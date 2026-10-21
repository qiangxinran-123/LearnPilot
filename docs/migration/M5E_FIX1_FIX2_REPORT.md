# M5-E FIX-1 + FIX-2 Report

## Scope

This maintenance change improves source visibility in the existing knowledge-detail experience and makes existing material learning tools easier to discover. It does not alter M5 Evidence, Mastery, Confidence, diagnostic scoring, or knowledge-map structure.

## FIX-1: verified source preview

`GET /api/courses/{course_id}/knowledge-nodes/{node_id}` now adds bounded source-preview fields to each source:

- `material_title`
- `original_text_excerpt`
- `original_text_truncated`

The backend returns a preview only when all of the following are true:

1. the source material belongs to the requested course;
2. its saved extraction status is usable;
3. `MaterialContent.segments` contains a non-empty text segment whose `source_reference` exactly matches the persisted M3 source reference.

The response is limited to 300 characters per source. It never reparses a file, calls an LLM, searches by node name, or returns a whole material. `KnowledgeSource.excerpt` remains a compatibility field but is not rendered as quoted source text. Missing, stale, cross-course, or invalid references return no preview and the UI shows a clear fallback with the existing material-detail link when safely available.

The knowledge detail route displays at most two verified previews. PDF page references are labelled as a verified page-content excerpt rather than an exact node quotation.

## FIX-2: material learning-tool discoverability

The existing course material list now shows a low-emphasis prompt only for `SUCCESS` materials:

> 打开资料，可生成摘要、制作学习卡片，并针对内容提问。

The existing entry button is labelled `查看资料与学习工具`; it still opens the original Material Detail route. Parsing, failed, unsupported, and empty-content records retain their real status and do not advertise unavailable tools. Material Detail keeps its existing summary, card, and Q&A flows, with clearer empty-state/help text only.

## Changed files

- `backend/app/api/knowledge.py`
- `backend/app/schemas/knowledge.py`
- `backend/app/services/knowledge_model_service.py`
- `backend/tests/test_m3a_knowledge_model.py`
- `frontend/src/types/knowledge.ts`
- `frontend/src/views/KnowledgeDetailView.vue`
- `frontend/src/components/knowledge/KnowledgeNodeDetail.vue`
- `frontend/src/views/CourseDetailView.vue`
- `frontend/src/views/MaterialDetailView.vue`
- `frontend/src/styles/base.css`
- targeted frontend tests, including `course-material-discoverability.spec.ts`

## Database migration

`DATABASE_MIGRATION: NOT REQUIRED`. The implementation reuses existing M2 material content and M3 source-reference records; no persisted schema changed.

## Preserved boundaries

- M4 ARCH-01 deterministic scoring: unchanged.
- M4 ARCH-02 historical reproducibility: unchanged.
- M4 ARCH-03 protected structured responses: unchanged.
- No FIX-3 investigation, M5-F, M6, new LLM call, parser run, or material-data rewrite was introduced.

## Verification

- Targeted backend source-reference tests: `16 passed`.
- Targeted backend Ruff lint: passed.
- Targeted backend Ruff format check: passed.
- Frontend TypeScript check: passed.
- Frontend full suite: `106/106 passed` under WSL Linux Node v24.22.0.
- Backend full suite: `299/299 passed` (reused because no production code changed after the recorded run).
- TypeScript, ESLint, production build, Ruff, Alembic, and `git diff --check`: passed.

## Final browser closure (2026-10-21)

ENV-01 is resolved. The cached Playwright 1.63.0 Chromium revision 1243 was reused; no project dependency or browser version changed. WSL required six Chromium runtime packages (`libnss3`, `libnspr4`, `libasound2t64` and three ALSA data/config packages), totaling about 2.2 MB download and 8.2 MB installed size.

Real Chromium checks used the running application at `http://127.0.0.1:5173` and an isolated acceptance copy at `http://127.0.0.1:5174` backed by `http://127.0.0.1:8001`. The isolated SQLite database lived under `/tmp`; the normal demo database was not written.

- FIX-1: PASS. Node 4 displayed two bounded, verified excerpts from the saved DOCX segments (`DOCX 第 60 段` and `DOCX 第 61 段`), distinguished them from the knowledge summary, collapsed additional sources, and preserved the Material Detail link. The page issued only GET requests and showed no blocking console error.
- FIX-2: PASS. Both successfully parsed materials displayed the learning-tool prompt and the `查看资料与学习工具` action. The action opened the existing Material Detail containing Content, Summary, Study Cards, and Material QA tabs without invoking a generation API. Processing/failed-state behavior remains covered by the existing component tests because the safe browser dataset contained only successful materials.
- Layout: PASS at 1024 px and 1440 px. The map, evidence detail, and material list had no horizontal document overflow.
- Regression: the existing M3 map, M5 mastery overlay, evidence explanation, and source preview remained available together. No FIX-3, M6, LLM generation, schema migration, or business-code change was introduced during closure.

Final maintenance status: `COMPLETE`. `DATABASE_MIGRATION: NOT REQUIRED`.
