# Contract Review Persistence - Handoff

Ngày cập nhật: 2026-05-17

## Mục tiêu

Lưu lâu dài dữ liệu `Rà soát hợp đồng` trên Supabase theo mô hình document-centric, tương tự ownership của Legal QA:

- Người dùng sở hữu một `contract_document` lâu dài.
- Mỗi document có nhiều `contract_document_versions`.
- Mỗi version hiện tại chỉ chạy review một lần.
- Mỗi run có một `contract_review_snapshot` để restore toàn bộ UI kết quả.
- File gốc được lưu trong Supabase Storage.
- Xóa document là soft delete, không xóa row và không xóa file storage.
- Giữ cấu trúc version lineage để sau này hỗ trợ AI sửa hợp đồng rồi tạo version mới.

## Ngữ cảnh từ session trước

File `docs/session_summary.md` mô tả các thay đổi UI trước đó:

- Giao diện đang dùng phong cách wobbly.
- Tab `Rà soát hợp đồng` đã được chỉnh để hiển thị kết quả rủi ro gọn hơn.
- Sidebar đã được style lại theo wobbly.
- Tab `Hỏi đáp pháp lý` đã có lịch sử hội thoại ở sidebar.

File `docs/persist-legal-qa-chat-sessions-handoff.md` mô tả phần Legal QA persistence đã làm:

- Frontend lấy backend token từ `/api/auth/backend-token`.
- FastAPI validate token trong `src/auth.py`.
- QA lưu `chat_conversations` và `chat_messages`.
- Sidebar QA history dùng event `legal-qa:history-changed`.

Contract Review persistence được thiết kế để đi theo cùng mô hình auth/ownership này.

## OpenSpec Change

Change đang dùng:

```text
openspec/changes/persist-contract-review-documents/
```

Các file chính:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/contract-review-persistence/spec.md`
- `specs/backend-api/spec.md`
- `specs/contract-review-ui/spec.md`

Trạng thái task gần nhất:

- Đã xong phần migration/schema, backend persistence, backend API, frontend API/state, frontend UI.
- Đã chạy compile Python.
- Đã chạy TypeScript check.
- Còn các bước verify runtime với Supabase thật.

Các task còn lại trong `tasks.md`:

- Apply migration vào Supabase project và chạy verify SQL.
- Upload hợp đồng hợp lệ, xác nhận tạo đủ document/version/run/storage object/snapshot.
- Refresh hoặc mở lại run completed, xác nhận restore từ snapshot, không chạy lại analysis.
- Upload file invalid, xác nhận không tạo data.
- Soft delete document, xác nhận biến khỏi history nhưng row/file vẫn còn.
- Confirm user này không đọc được dữ liệu user khác.

## Database

Migration mới:

```text
infra/supabase/007_contract_review_documents.sql
```

Verify SQL:

```text
infra/supabase/verify_contract_review_documents.sql
```

Storage bucket:

```text
contract-review-files
```

Schema mới:

```text
contract_documents
  id uuid
  user_id uuid references users(id)
  original_filename text
  display_name text
  created_at timestamptz
  updated_at timestamptz
  deleted_at timestamptz

contract_document_versions
  id uuid
  document_id uuid references contract_documents(id)
  user_id uuid references users(id)
  version_number integer
  source_type text
  parent_version_id uuid references contract_document_versions(id)
  source_run_id uuid references contract_review_runs(id)
  filename text
  content_type text
  source_format text
  file_size_bytes bigint
  storage_path text
  created_at timestamptz
  updated_at timestamptz
  deleted_at timestamptz

contract_review_runs
  id uuid
  document_id uuid references contract_documents(id)
  version_id uuid references contract_document_versions(id)
  user_id uuid references users(id)
  status text
  progress integer
  started_at timestamptz
  completed_at timestamptz
  error text
  created_at timestamptz
  updated_at timestamptz
  deleted_at timestamptz

contract_review_snapshots
  id uuid
  run_id uuid references contract_review_runs(id)
  user_id uuid references users(id)
  schema_version integer
  result_json jsonb
  created_at timestamptz
  updated_at timestamptz
```

Ghi chú thiết kế:

- `contract_documents` là identity lâu dài của hợp đồng.
- `contract_document_versions` giữ metadata file và `storage_path`.
- `contract_review_runs` giữ trạng thái chạy analysis.
- `contract_review_snapshots.result_json` là nguồn restore chính cho UI.
- Chưa dùng RLS/Supabase Auth JWT cho flow này; ownership đang enforce trong FastAPI giống Legal QA.

## Backend

File mới:

```text
infra/api/contract_store.py
```

Chức năng chính:

- Đọc Supabase config từ env, bao gồm `frontend/.env.local`.
- Upload file vào Supabase Storage.
- Tạo signed URL cho file.
- Create/get/list/update:
  - document
  - version
  - run
  - snapshot
- Soft delete document.
- Mọi read/write đều nhận `user_id` và filter theo owner.

File route chính:

```text
infra/api/contract_routes.py
```

Các API quan trọng:

```text
POST   /api/contracts/upload
GET    /api/contracts/{job_id}/status
GET    /api/contracts/history
DELETE /api/contracts/documents/{document_id}
GET    /api/contracts/documents/{doc_title}
```

Luồng upload hiện tại:

1. Frontend gửi file với Bearer backend token.
2. FastAPI validate user bằng `get_current_user`.
3. Backend tạo `contract_documents`.
4. Backend upload file vào Supabase Storage.
5. Backend tạo `contract_document_versions`.
6. Backend tạo `contract_review_runs`.
7. Background task chạy parser + review pipeline.
8. Khi xong, backend lưu `contract_review_snapshots.result_json`.
9. Run được mark `completed`; nếu lỗi thì mark `failed`.

Compatibility:

- API vẫn gọi identifier là `jobId` ở frontend.
- Nội bộ `jobId` đang map sang `contract_review_runs.id`.

## Frontend API

File chính:

```text
frontend/src/lib/api-client.ts
frontend/src/lib/api-contract.ts
frontend/src/lib/mock-api-contract.ts
```

Thay đổi chính:

- `api-client.ts` export `getAuthToken`.
- Có `apiUpload` để upload FormData kèm Bearer token.
- `api-contract.ts` thêm:
  - `documentId`
  - `versionId`
  - `fileUrl`
  - `previewText`
  - `sourceFormat`
  - `deleteDocument(documentId)`

Contract Review frontend vẫn dùng `ContractJob.id` như `jobId`, nhưng id đó là persisted run id.

## Frontend UI

File chính:

```text
frontend/src/app/(app)/contract-review/page.tsx
frontend/src/app/(app)/dashboard/page.tsx
frontend/src/components/layout/sidebar.tsx
```

Đã làm:

- Contract Review page restore kết quả từ persisted snapshot.
- Dashboard recent contract entries dùng history thật thay vì mock data.
- Sidebar đã có Contract Review history giống Legal QA:
  - Hiện dưới item `Rà soát hợp đồng`.
  - Có arrow show/hide.
  - Scroll sau nhiều item.
  - Click item đi tới `/contract-review?jobId=...`.
  - Có delete button để soft-delete document.
  - Listen event `contract-review:history-changed`.

Event đang dùng:

```text
contract-review:history-changed
```

## Lỗi Preview / Font Đã Trace

Triệu chứng:

- Preview trước khi upload xem được.
- Preview sau khi restore từ Supabase bị lỗi ký tự tiếng Việt, trông giống lỗi font.

Kết luận:

- Snapshot trong Supabase có tiếng Việt đúng.
- Vấn đề không phải font.
- Vấn đề là frontend lấy signed URL của file `.md` hoặc text rồi đưa vào `PDFViewer`, trong khi `PDFViewer` ép iframe render dạng PDF.
- Browser không render đúng text file theo đường đó, tạo cảm giác mojibake/font lỗi.

Fix đã áp dụng:

- Trong `frontend/src/app/(app)/contract-review/page.tsx`, restore preview dùng `buildRestoredPreviewUrl(status)`.
- Nếu `sourceFormat === "pdf"` thì dùng trực tiếp `fileUrl`.
- Nếu không phải PDF, frontend fetch signed URL, dựng lại `File`, gọi lại `fileToPdfBlob(file)`, tạo object URL rồi render bằng `PDFViewer`.
- Nếu conversion fail thì fallback về `previewText`.

Parser cũng đã được tăng độ bền:

```text
src/contract/parser.py
```

- Thêm `repair_mojibake_text`.
- Thêm `_text_quality_score`.
- Đọc text bằng các encoding: `utf-8`, `utf-8-sig`, `cp1258`, `latin-1`.
- MinerU markdown output cũng được repair trước khi trả về.

## Verification Đã Chạy

Python compile:

```bash
python3 -m compileall infra/api src/contract/parser.py src/auth.py src/config.py
```

TypeScript:

```bash
cd frontend
npx tsc --noEmit
```

Cả hai đã pass ở lần chạy gần nhất.

Đã query Supabase thực tế một lần để kiểm tra run:

```text
d23e532b-e288-4b94-af00-5b5379cb5c89
```

Kết quả: `previewText` trong snapshot là tiếng Việt đúng. Điều này xác nhận lỗi nằm ở đường render preview, không nằm ở dữ liệu đã lưu.

## Environment

Các biến cần có trong `frontend/.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
AUTH_SECRET=...
NEXTAUTH_URL=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_USE_MOCK_API=false
SUPABASE_CONTRACT_REVIEW_BUCKET=contract-review-files
```

Lưu ý:

- `SUPABASE_SERVICE_ROLE_KEY` cần cho backend thao tác PostgREST/Storage.
- `NEXT_PUBLIC_USE_MOCK_API=false` để frontend gọi API thật.
- Nếu đổi env thì restart cả frontend và backend.

## Known Risks / Điểm Cần Chú Ý

- Migration `007` cần được apply trên Supabase thật trước khi test end-to-end.
- Storage bucket private nên restore preview phụ thuộc signed URL.
- Sidebar delete hiện soft-delete document và reload list; nếu đang đứng trên chính run vừa xóa, page hiện tại có thể vẫn còn state cũ cho tới khi chuyển trang/reload.
- `contract_review_snapshots.result_json` là JSONB snapshot, tiện restore UI nhưng chưa tối ưu cho analytics/search chi tiết.
- Chưa triển khai AI rewrite; schema đã có `source_type`, `parent_version_id`, `source_run_id` để dùng sau.

## Suggested Next Session Steps

1. Mở `openspec/changes/persist-contract-review-documents/tasks.md`.
2. Apply `infra/supabase/007_contract_review_documents.sql` vào Supabase nếu chưa apply.
3. Chạy `infra/supabase/verify_contract_review_documents.sql`.
4. Restart backend:

```bash
uvicorn infra.api.app:app --port 8000 --log-level info
```

5. Restart frontend:

```bash
cd frontend
npm run dev
```

6. Vào `/contract-review`, upload một file PDF hoặc DOCX.
7. Xác nhận Supabase có đủ:

```text
contract_documents: 1 row
contract_document_versions: 1 row
contract_review_runs: 1 row
contract_review_snapshots: 1 row
storage bucket contract-review-files: 1 object
```

8. Refresh trang hoặc mở `/contract-review?jobId=<run_id>`, xác nhận UI restore từ snapshot.
9. Kiểm tra sidebar `Rà soát hợp đồng` hiển thị history giống QA.
10. Test soft delete trong sidebar, xác nhận item biến khỏi history nhưng row có `deleted_at`.

