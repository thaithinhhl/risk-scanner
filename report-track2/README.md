# Rà soát chính sách và hợp đồng - Pháp lý AI

Link github:

Link team name:

Link video demo:

Link url project: 

## Mô tả ngắn gọn
**Rà soát chính sách và hợp đồng - Pháp lý AI** là một hệ thống Trợ lý pháp luật AI đột phá dành riêng cho môi trường pháp lý Việt Nam. Bằng việc kết hợp sức mạnh của Mô hình ngôn ngữ lớn (LLMs) và Đồ thị tri thức (GraphRAG với Neo4j), dự án số hóa và liên kết hơn 21.000 văn bản pháp luật, tạo ra một cỗ máy thông minh có khả năng tự động đọc hiểu, trích xuất và rà soát các rủi ro trong hợp đồng dựa trên các quy định hiện hành của pháp luật Việt Nam.

## Mục tiêu và Vấn đề giải quyết
**Vấn đề:** 
- Quá trình đọc duyệt và rà soát hợp đồng thủ công tốn rất nhiều thời gian của các chuyên gia pháp lý.
- Rất dễ bỏ sót các điều khoản bất lợi (như mức phạt vi phạm vượt quá mức luật định, điều khoản bất khả kháng mập mờ, bẫy gia hạn tự động, v.v.).
- Việc đối chiếu một điều khoản với hàng ngàn văn bản luật liên quan (Luật Dân sự, Luật Doanh nghiệp, các Nghị định...) là vô cùng phức tạp.

**Mục tiêu:**
- Tự động hóa quá trình rà soát hợp đồng với độ chính xác cao dựa trên kho dữ liệu pháp luật Việt Nam.
- Đóng vai trò như một trợ lý pháp lý ảo hoạt động 24/7, phát hiện tức thời các rủi ro, cảnh báo vi phạm và đề xuất hướng sửa đổi bảo vệ quyền lợi cho người dùng.

##  Tính năng chính
- 📂 **Trích xuất điều khoản thông minh:** Tự động đọc và bóc tách các điều khoản từ file tài liệu (PDF, Word).
- 🚨 **Đánh giá rủi ro & Cảnh báo (Risk Scoring):** Áp dụng luật Việt Nam để cắm cờ cảnh báo rủi ro (🔴 Nguy hiểm/Vi phạm luật, 🟡 Rủi ro cần đàm phán lại, 🟢 An toàn/Chuẩn mực).
- 📝 **Đề xuất chỉnh sửa (Redlines):** Tự động đề xuất các đoạn text thay thế cho các điều khoản rủi ro.
- 🔗 **Truy xuất luật chính xác (GraphRAG):** Trích dẫn chính xác điều, khoản, điểm của văn bản luật liên quan (hạn chế tối đa ảo giác AI - Hallucination).
- 💬 **Trợ lý Hỏi - Đáp pháp lý (QA):** Giao diện chat trực tiếp với AI để giải đáp thắc mắc về luật và chính sách.
- 🕸️ **Knowledge Graph Admin Portal:** Cổng quản trị trực quan hóa các mối quan hệ (Sửa đổi, Thay thế, Căn cứ) giữa các bộ luật.

---

## ⚙️ Hướng dẫn cài đặt

**1. Yêu cầu hệ thống:**
- Python 3.10+
- Node.js 18+
- Neo4j 5.18.0 (Có cài sẵn Java 17)
- RAM: >= 8GB

**2. Clone dự án và cài đặt môi trường Python:**
```bash
# Clone repository
git clone <repository_url>
cd nhom104-risk-scanner

# Tạo và kích hoạt môi trường ảo
python -m venv .venv
source .venv/bin/activate  # (Với Windows: .venv\Scripts\activate)

# Cài đặt các thư viện Python
pip install -r requirements.txt
```

**3. Cài đặt và cấu hình Neo4j (Database):**
```bash
# (Dành cho Ubuntu/Debian) Chạy script cài đặt Neo4j tự động
chmod +x infra/neo4j/setup.sh
sudo ./infra/neo4j/setup.sh
```

**4. Cấu hình biến môi trường:**
Tạo file `.env` từ file mẫu và điền các thông tin bảo mật (API Key, Mật khẩu Neo4j...):
```bash
cp .env.example .env
# Mở file .env và cập nhật NEO4J_PASSWORD, OPENAI_API_KEY...
```

**5. Cài đặt Frontend:**
```bash
cd frontend
npm install
cd ..
```

---

## 🚀 Hướng dẫn chạy dự án

Để khởi động toàn bộ hệ thống, bạn cần bật các dịch vụ sau trong các terminal khác nhau:

**1. Khởi động Cơ sở dữ liệu đồ thị (Neo4j):**
```bash
sudo systemctl start neo4j
```

**2. Nạp dữ liệu và Knowledge Graph (Chỉ chạy 1 lần đầu tiên):**
```bash
# Đảm bảo bạn đang ở môi trường ảo python
python -m src.data_pipeline.pipeline
```

**3. Khởi động Backend API (FastAPI):**
```bash
# Mở terminal mới, kích hoạt .venv
uvicorn infra.api.app:app --host 0.0.0.0 --port 8000 --reload
```

**4. Khởi động Giao diện Người dùng (Next.js Frontend):**
```bash
# Mở terminal mới
cd frontend
npm run dev
# App sẽ chạy tại: http://localhost:3000
```

**5. Khởi động Admin Portal (Streamlit):**
```bash
# Mở terminal mới, kích hoạt .venv
streamlit run app.py
# Admin Dashboard sẽ chạy tại: http://localhost:8501
```

---

## 📖 Hướng dẫn sử dụng sản phẩm

### 1. Dành cho Người dùng cuối (Qua Frontend - `localhost:3000`)
- **Đăng nhập/Đăng ký:** Tạo tài khoản để lưu trữ lịch sử các hợp đồng.
- **Tải lên hợp đồng:** Chọn file hợp đồng (PDF hoặc Word) cần rà soát và tải lên hệ thống.
- **Xem Báo cáo Rủi ro:** Sau ít phút phân tích, màn hình sẽ hiển thị chi tiết từng điều khoản, kèm theo các nhãn màu cảnh báo rủi ro (Đỏ, Vàng, Xanh).
- **Xem đề xuất & Trích dẫn:** Click vào các điều khoản bị gắn cờ đỏ/vàng để xem đề xuất sửa đổi và đọc trích dẫn gốc của bộ luật Dân sự/Doanh nghiệp quy định về vấn đề đó.
- **Hỏi đáp:** Sử dụng khung Chat để hỏi thêm AI về một điều khoản cụ thể.

### 2. Dành cho Quản trị viên/Kỹ sư dữ liệu (Qua Admin Portal - `localhost:8501`)
- **Tra cứu văn bản:** Nhập số hiệu văn bản (Ví dụ: `46/2014/NĐ-CP`) để xem metadata và nội dung HTML đã được làm sạch.
- **Đồ thị quan hệ:** Nhập ID văn bản để xem sơ đồ mạng lưới các luật liên quan (Luật nào bị thay thế, luật nào sửa đổi bổ sung).
- **Thống kê:** Xem biểu đồ tổng quan về lượng dữ liệu hiện có trong Knowledge Graph.

## 3. Dành cho người dùng sản phầm - xem qua video hướng dẫn

---
