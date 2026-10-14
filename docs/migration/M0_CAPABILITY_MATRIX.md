# LearnPilot V1 — M0 Capability Matrix

Status note: Code Exists means source was found. Runtime Verified requires a M0 command or existing test. It is not inferred from documentation or a route name.

| Capability | Code Exists | Backend | Frontend | Integrated | Runtime Verified | Decision |
|---|---:|---:|---:|---:|---:|---|
| Health and API metadata | Yes | Yes | No | N/A | Yes | KEEP |
| Native static workspace shell | Yes | Static host | Yes | Yes | Static resources only | REFACTOR |
| Read seeded course catalog | Yes | Yes | Yes | Yes | Yes | REFACTOR |
| Read/create material metadata | Yes | Yes | Partial | Partial | Yes | REFACTOR |
| Local JSON material persistence | Yes | Yes | No | N/A | Yes | REFACTOR |
| File upload/storage | Yes | Yes | TXT/MD only | Partial | TXT/MD/PDF only | REFACTOR |
| TXT/MD text extraction | Yes | Yes | Displayed | Yes | Yes | REFACTOR |
| Material keyword search | Yes | Yes | Yes | Yes | Yes | REFACTOR |
| Mock summary | Yes | Yes | Yes | Yes | Yes, mock only | REFACTOR |
| Mock learning cards | Yes | Yes | Yes | Yes | Yes, mock only | REFACTOR |
| Hard-coded project status and legacy hello | Yes | Yes | No | No | Status only; hello fails | DEPRECATE |
| PDF text extraction | No | No | No | No | No | NEW |
| DOCX text extraction | No | No | No | No | No | NEW |
| PPTX text extraction | No | No | No | No | No | NEW |
| Real LLM provider adapter | No | No | No | No | No | NEW |
| AI Chat/Tutor | No | No | No | No | No | NEW |
| File QA grounded in materials | No | No | No | No | No | NEW |
| Course CRUD and ownership | Partial read-only | Partial | Partial | Partial | Read-only only | NEW |
| User authentication/authorization | No | No | No | No | No | NEW |
| Database/ORM/migrations | No | No | No | No | No | NEW |
| Dashboard learning cockpit | No | No | No | No | No | NEW |
| Diagnostic tests/questions/responses | No | No | No | No | No | NEW |
| Learning Evidence | No | No | No | No | No | NEW |
| Knowledge nodes/edges/prerequisites | No | No | No | No | No | NEW |
| Mastery score/confidence/snapshots | No | No | No | No | No | NEW |
| Recommendation, learning session, adaptive exercise | No | No | No | No | No | NEW |
| Progress trends, weak areas, history, review risk | No | No | No | No | No | NEW |

Decision counts:

| Decision | Count | Meaning |
|---|---:|---|
| KEEP | 1 | Existing operational asset can be retained directly. |
| REFACTOR | 8 | Existing behavior has product value but needs new structure, data model, security, or implementation. |
| DEPRECATE | 1 | Demo-only or invalid endpoint does not belong in V1. |
| NEW | 16 | Required LearnPilot capability absent from LearnPilot. |

Existing LearnPilot feature count is 10: 1 KEEP, 8 REFACTOR, and 1 DEPRECATE. NEW rows are V1 gaps; they are not claimed as existing LearnPilot implementation.
