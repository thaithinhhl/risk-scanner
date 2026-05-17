## 👥 Phân công nhiệm vụ (Team Roles)

Dự án được xây dựng bởi 3 thành viên, mỗi người phụ trách một mảng chuyên biệt để đảm bảo luồng dữ liệu đi từ thô đến ứng dụng AI hoàn chỉnh:

| Thành viên | Vai trò & Trách nhiệm chính | Các module phụ trách (Source Code) |
| :--- | :--- | :--- |
| **Người A**<br>*(Data & Infra)*  |- Thu thập, chuẩn hóa và làm sạch dữ liệu (Hơn 150k văn bản).<br>- Thiết kế và cấu hình **Neo4j Graph Database**.<br>- Nạp dữ liệu (Ingest) Nodes và Edges vào đồ thị.<br>- Xây dựng cổng quản trị **Admin Portal** bằng Streamlit. | - `src/data_pipeline/`<br>- `infra/neo4j/`<br>- `app.py` (Streamlit) |
| **Người B**<br>*(Graph Processing)*| - Trích xuất quan hệ giữa các bộ luật (Cross-reference) bằng mô hình ngôn ngữ (LLM).<br>- Phân rã (Segmentation) các tài liệu pháp luật thành các Điều, Khoản, Điểm.<br>- Đảm bảo cấu trúc đồ thị tối ưu cho việc truy xuất thông tin (Retrieval). | - `src/cross_reference/`<br>- `src/segmentation/`<br>- `src/effective_text/` |
| **Người C**<br>*(AI & App)* | - Xây dựng luồng **Contract Review Pipeline** (Bóc tách điều khoản, đánh giá rủi ro).<br>- Xây dựng hệ thống GraphRAG đối chiếu luật và Citation Verifier chống ảo giác.<br>- Phát triển **FastAPI Backend** (Async/SSE) và **Next.js Frontend**. | - `src/contract/`<br>- `src/llm/`<br>- `infra/api/`<br>- `frontend/` |

---

## 📅 Chi tiết Task / Log Work

Dưới đây là chi tiết các hạng mục công việc đã thực hiện qua các tuần, kèm theo người phụ trách và trạng thái hoàn thành:

| Thời gian (Tuần) | Công việc (Task) | Trạng thái | Thành viên phụ trách | Ghi chú (Khó khăn & Giải pháp) |
| :---: | :--- | :---: | :---: | :--- |
| **Tuần 2** | Thống nhất và thu hẹp scope đề tài | ✅ Done | Cả team | Đã chốt được đề tài phù hợp với nguồn lực. |
| **Tuần 2** | Thiết kế data pipeline và cấu trúc dữ liệu | ✅ Done | Người A | Dữ liệu phức tạp, cần tham vấn Coach. |
| **Tuần 2** | Nghiên cứu giải pháp RAG cho văn bản luật | ✅ Done | Người B | Cách liên kết ngữ cảnh từ Thông tư lên Luật gốc. |
| **Tuần 3** | Xây dựng bản MVP Agent rà soát hợp đồng | ✅ Done | Người C | Đã có thể trả lời QA cơ bản. |
| **Tuần 3** | Tối ưu tốc độ RAG và xây dựng bộ test | ✅ Done | Người B | |
| **Tuần 3** | Xử lý độ trễ LLM và liên kết chéo phức tạp | ✅ Done | Người B, C | Giải pháp: Áp dụng GraphRAG, dùng "GraphEval". |
| **Tuần 4** | Xây dựng Graph RAG cấp độ văn bản | ✅ Done | Người B | Đã trích xuất được relationship cơ bản. |
| **Tuần 4** | Triển khai Relationship chi tiết (Điều -> Điều) | ✅ Done | Người B | |
| **Tuần 4** | Giải quyết liên kết chéo giữa từng điều luật | ✅ Done | Người B | Thử nghiệm trích xuất bằng Regex và LLM. |
| **Tuần 5** | Xong Graph giữa các điều khoản, cải tiến chunking | ✅ Done | Người B | Chuyển BM25 sang OpenSearch (đổi trọng số). |
| **Tuần 5** | Viết Crawler bổ sung dữ liệu thuvienphapluat | ✅ Done | Người A | |
| **Tuần 5** | Xây dựng Graph RAG cho Nghị quyết, Thông tư | ✅ Done | Người B | |
| **Tuần 5** | Xử lý search sai do thiếu content, format khác biệt | ✅ Done | Người A | Giải pháp: Dùng Crawler cào bù nội dung bị thiếu. |
| **Tuần 6** | Xây dựng lại bản Specs chi tiết (chống sai dataset)| ✅ Done | Cả team | |
| **Tuần 6** | Bổ sung đủ dữ liệu còn thiếu, tối ưu Semantic | ✅ Done | Người A | Vẫn còn vấn đề nhỏ về độ chính xác. |
| **Tuần 6** | Deploy hệ thống lên Cloud, phân việc nước rút | ✅ Done | Cả team | Deadline Demo Day cận kề, team chạy sprint. |
| **Tuần 7** | Xây dựng CSDL 2.700 văn bản lõi | ✅ Done | Người A | Đạt 80% mục tiêu đề ra. |
| **Tuần 7** | Hoàn thiện Login (Google, Github) & UI/UX Next.js | ✅ Done | Người C | |
| **Tuần 7** | Hoàn thiện module xác thực, phân quyền | ✅ Done | Người C | |
| **Tuần 7** | Regex fail do cấu trúc luật VN lộn xộn (Edge cases) | ✅ Done | Người B | Chấp nhận tối ưu thủ công vì giới hạn chi phí LLM. |
