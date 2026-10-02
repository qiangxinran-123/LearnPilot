from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CoursesApiPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.data_file = self.root / "courses.json"
        self.upload_dir = self.root / "uploads"
        self.database_file = self.root / "learnpilot.sqlite3"
        self.database_url = f"sqlite+pysqlite:///{self.database_file}"
        self.data_file.write_text(
            json.dumps(
                {
                    "courses": [
                        {
                            "id": 1,
                            "name": "Computer Organization",
                            "semester": "Junior Year",
                            "description": "Course materials and notes.",
                        },
                        {
                            "id": 7,
                            "name": "Data Structures",
                            "semester": "Sophomore Year",
                            "description": "Stacks, queues, trees, and graphs.",
                        },
                    ],
                    "materials": {
                        "1": [
                            {
                                "id": 101,
                                "title": "Cache Memory Notes",
                                "type": "note",
                                "summary": "Cache basics.",
                            }
                        ],
                        "7": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        self.source_before = self.data_file.read_bytes()
        self.port = self._free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": self.database_url,
                "UPLOAD_ROOT": str(self.upload_dir),
                "MAX_UPLOAD_BYTES": "1024",
                "LOG_LEVEL": "WARNING",
                "LLM_MODE": "mock",
            }
        )
        self._run_migrations()
        self._run_importer()
        self._start_server()

    def tearDown(self) -> None:
        self._stop_server()
        self.assertEqual(self.data_file.read_bytes(), self.source_before)
        self.tmpdir.cleanup()

    def test_courses_are_loaded_from_relational_import(self) -> None:
        response = self._request("GET", "/api/courses")

        self.assertEqual(response["count"], 2)
        self.assertEqual(response["courses"][1]["id"], 7)
        self.assertEqual(response["courses"][1]["name"], "Data Structures")

    def test_course_detail_is_available(self) -> None:
        response = self._request("GET", "/api/courses/1")

        self.assertEqual(response["id"], 1)
        self.assertEqual(response["semester"], "Junior Year")

    def test_materials_are_loaded_from_relational_import(self) -> None:
        response = self._request("GET", "/api/courses/1/materials")

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["materials"][0]["id"], 101)

    def test_created_material_survives_service_restart(self) -> None:
        created = self._request(
            "POST",
            "/api/courses/1/materials",
            {
                "title": "Pipeline Review",
                "type": "slide",
                "summary": "Pipeline stages and hazards.",
            },
        )

        self.assertEqual(created["id"], 102)
        self._restart_server()
        materials = self._request("GET", "/api/courses/1/materials")
        self.assertEqual(materials["materials"][-1]["title"], "Pipeline Review")

    def test_upload_txt_file_is_saved_and_path_is_redacted(self) -> None:
        created = self._multipart_request(
            "/api/courses/1/materials/upload",
            "lecture-notes.txt",
            b"Cache mapping and replacement policies.",
            "text/plain",
        )

        self.assertEqual(created["filename"], "lecture-notes.txt")
        self.assertTrue(created["extracted"])
        self.assertEqual(created["text_length"], 39)
        self.assertNotIn("file_path", created)
        self.assertNotIn(str(self.upload_dir), json.dumps(created))
        self._restart_server()
        materials = self._request("GET", "/api/courses/1/materials")
        self.assertEqual(materials["materials"][-1]["id"], created["id"])

    def test_upload_md_file_extracts_text(self) -> None:
        content = b"# Machine Learning\n\nGradient descent and model evaluation."
        created = self._multipart_request(
            "/api/courses/1/materials/upload",
            "review.md",
            content,
            "text/markdown",
        )

        self.assertTrue(created["extracted"])
        self.assertEqual(created["text_length"], len(content))
        self.assertEqual(created["text_preview"], content.decode())

    def test_corrupt_pdf_is_securely_stored_with_parse_failure_status(self) -> None:
        created = self._multipart_request(
            "/api/courses/1/materials/upload",
            "slides.pdf",
            b"%PDF-1.4 binary placeholder",
            "application/pdf",
        )

        self.assertFalse(created["extracted"])
        self.assertEqual(created["extraction_status"], "PARSE_FAILED")
        self.assertEqual(created["extraction_error_code"], "PDF_PARSE_ERROR")

    def test_txt_material_can_generate_and_persist_mock_summary(self) -> None:
        created = self._upload_text("summary-notes.txt", b"Cache memory improves average access time.")
        summary = self._request("POST", f"/api/materials/{created['id']}/summary", {})

        self.assertTrue(summary["summary_generated"])
        self.assertEqual(summary["summary_method"], "mock")
        self.assertTrue(summary["ai_summary"].startswith("Mock summary: "))

    def test_summary_for_unknown_material_returns_not_found(self) -> None:
        status, response = self._request_with_error("POST", "/api/materials/9999/summary", {})

        self.assertEqual(status, 404)
        self.assertEqual(response["detail"], "Material not found")
        self.assertEqual(response["error"]["code"], "NOT_FOUND")

    def test_summary_without_text_returns_bad_request(self) -> None:
        status, response = self._request_with_error("POST", "/api/materials/101/summary", {})

        self.assertEqual(status, 400)
        self.assertEqual(response["detail"], "Material has not been parsed successfully.")
        self.assertEqual(response["error"]["code"], "MATERIAL_NOT_PARSED")

    def test_repeated_summary_updates_existing_material(self) -> None:
        created = self._upload_text("repeat-summary.txt", b"Pipeline stages and hazards.")
        first = self._request("POST", f"/api/materials/{created['id']}/summary", {})
        time.sleep(0.002)
        second = self._request("POST", f"/api/materials/{created['id']}/summary", {})

        self.assertEqual(second["id"], first["id"])
        self.assertNotEqual(second["summary_updated_at"], first["summary_updated_at"])

    def test_ai_summary_material_can_generate_mock_cards(self) -> None:
        created = self._upload_text(
            "card-notes.txt",
            b"Cache locality improves memory performance. Review cache hit and cache miss.",
        )
        self._request("POST", f"/api/materials/{created['id']}/summary", {})
        generated = self._request("POST", f"/api/materials/{created['id']}/cards", {})

        self.assertEqual(generated["count"], 5)
        self.assertTrue(generated["cards_generated"])
        self.assertEqual(generated["cards"][0]["source_material_id"], created["id"])

    def test_repeated_card_generation_replaces_existing_cards(self) -> None:
        created = self._upload_text("repeat-cards.txt", b"Pipelines improve instruction throughput.")
        first = self._request("POST", f"/api/materials/{created['id']}/cards", {})
        time.sleep(0.002)
        second = self._request("POST", f"/api/materials/{created['id']}/cards", {})

        self.assertEqual(second["count"], 5)
        self.assertEqual(
            [card["id"] for card in second["cards"]],
            [card["id"] for card in first["cards"]],
        )

    def test_card_generation_returns_not_found_for_unknown_material(self) -> None:
        status, response = self._request_with_error("POST", "/api/materials/9999/cards", {})

        self.assertEqual(status, 404)
        self.assertEqual(response["detail"], "Material not found")

    def test_card_generation_rejects_material_without_text(self) -> None:
        created = self._request(
            "POST",
            "/api/courses/1/materials",
            {"title": "Empty Material", "type": "note", "summary": ""},
        )
        status, response = self._request_with_error(
            "POST",
            f"/api/materials/{created['id']}/cards",
            {},
        )

        self.assertEqual(status, 400)
        self.assertEqual(response["detail"], "Material has not been parsed successfully.")
        self.assertEqual(response["error"]["code"], "MATERIAL_NOT_PARSED")

    def test_search_matches_material_title_case_insensitively(self) -> None:
        response = self._request("GET", "/api/materials/search?q=CACHE+MEMORY")

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["materials"][0]["id"], 101)

    def test_search_matches_uploaded_text_preview(self) -> None:
        created = self._upload_text(
            "graph-notes.txt",
            b"Graph traversal visits vertices through a queue or stack.",
        )
        response = self._request("GET", "/api/materials/search?q=TRAVERSAL")

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["materials"][0]["id"], created["id"])

    def test_search_matches_generated_mock_summary(self) -> None:
        created = self._upload_text(
            "dynamic-programming.txt",
            b"Dynamic programming solves overlapping subproblems efficiently.",
        )
        self._request("POST", f"/api/materials/{created['id']}/summary", {})
        response = self._request("GET", "/api/materials/search?q=mock+summary")

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["materials"][0]["id"], created["id"])

    def test_search_respects_course_filter(self) -> None:
        matching = self._request("GET", "/api/materials/search?q=cache&course_id=1")
        other = self._request("GET", "/api/materials/search?q=cache&course_id=7")

        self.assertEqual(matching["count"], 1)
        self.assertEqual(other["count"], 0)

    def test_search_returns_empty_result_when_no_material_matches(self) -> None:
        response = self._request("GET", "/api/materials/search?q=unmatched-keyword")

        self.assertEqual(response["count"], 0)
        self.assertEqual(response["materials"], [])

    def test_search_rejects_missing_and_blank_keyword(self) -> None:
        missing_status, missing_response = self._request_with_error("GET", "/api/materials/search")
        blank_status, blank_response = self._request_with_error("GET", "/api/materials/search?q=%20%20")

        self.assertEqual(missing_status, 400)
        self.assertEqual(blank_status, 400)
        self.assertEqual(missing_response["error"]["code"], "EMPTY_SEARCH_QUERY")
        self.assertEqual(blank_response["error"]["code"], "EMPTY_SEARCH_QUERY")

    def test_upload_rejects_unsupported_extension(self) -> None:
        status, response = self._multipart_request(
            "/api/courses/1/materials/upload",
            "notes.exe",
            b"not a course document",
            "application/octet-stream",
            expect_error=True,
        )

        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "UNSUPPORTED_FILE_TYPE")

    def test_upload_rejects_unknown_course_and_missing_file(self) -> None:
        status, response = self._multipart_request(
            "/api/courses/999/materials/upload",
            "notes.txt",
            b"course does not exist",
            "text/plain",
            expect_error=True,
        )
        self.assertEqual(status, 404)
        missing_status, missing_response = self._multipart_request(
            "/api/courses/1/materials/upload",
            None,
            b"",
            "text/plain",
            expect_error=True,
        )
        self.assertEqual(missing_status, 400)
        self.assertEqual(missing_response["error"]["code"], "INVALID_FILENAME")

    def _upload_text(self, filename: str, content: bytes) -> dict[str, object]:
        return self._multipart_request(
            "/api/courses/1/materials/upload",
            filename,
            content,
            "text/plain",
        )

    def _request(self, method: str, path: str, payload: object | None = None) -> dict[str, object]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _request_with_error(
        self,
        method: str,
        path: str,
        payload: object | None = None,
    ) -> tuple[int, dict[str, object]]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def _multipart_request(
        self,
        path: str,
        filename: str | None,
        content: bytes,
        content_type: str,
        expect_error: bool = False,
    ) -> dict[str, object] | tuple[int, dict[str, object]]:
        boundary = "----LearnPilotTestBoundary"
        parts: list[bytes] = []
        if filename is not None:
            disposition = f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            parts.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    disposition.encode(),
                    f"Content-Type: {content_type}\r\n\r\n".encode(),
                    content,
                    b"\r\n",
                ]
            )
        parts.append(f"--{boundary}--\r\n".encode())
        request = Request(
            f"{self.base_url}{path}",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result if not expect_error else (response.status, result)
        except HTTPError as error:
            with error:
                result = json.loads(error.read().decode("utf-8"))
            if not expect_error:
                raise
            return error.code, result

    def _run_migrations(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=self.environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _run_importer(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.scripts.import_legacy_json",
                "--database-url",
                self.database_url,
                "--source",
                str(self.data_file),
            ],
            env=self.environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _start_server(self) -> None:
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            env=self.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_server()

    def _stop_server(self) -> None:
        if not hasattr(self, "server"):
            return
        self.server.terminate()
        try:
            self.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.wait(timeout=5)

    def _restart_server(self) -> None:
        self._stop_server()
        self._start_server()

    def _wait_for_server(self) -> None:
        last_error: Exception | None = None
        for _ in range(50):
            if self.server.poll() is not None:
                self.fail("API server exited before becoming ready")
            try:
                self._request("GET", "/health")
                return
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                time.sleep(0.1)
        self.fail(f"API server did not become ready: {last_error}")

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
