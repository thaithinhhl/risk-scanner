# Báo cáo Tổng Hợp Các Thay Đổi & Cải Tiến Giao Diện (Version 1.0)
*Ngày cập nhật: 17/05/2026*
*Nhánh Git hiện tại: `cuong-T2.4`*

---

## 1. Tổng Quan Yêu Cầu Của Người Dùng
Mục tiêu chính của phiên làm việc này là nâng cấp giao diện của ứng dụng Rà soát Hợp đồng & Hỏi đáp Pháp lý sang phong cách **Wobbly (bong bóng lượn sóng vẽ tay đầy tính nghệ thuật)**, tinh chỉnh cơ chế hiển thị rủi ro hợp đồng và tối ưu hóa trải nghiệm tương tác gọn gàng, trực quan.

---

## 2. Chi Tiết Các Thay Đổi Đã Thực Hiện

### 2.1. Cải Tiến Tab "Rà Soát Hợp Đồng" (`frontend/src/app/(app)/contract-review/page.tsx`)
- **Ẩn bớt thông tin chi tiết điều luật mặc định:** 
  - Chỉ hiển thị nội dung tóm tắt màu xanh của điều luật trước. 
  - Ẩn phần trích dẫn màu trắng mặc định đi. 
  - Khi người dùng bấm vào nút trích dẫn (citation button) thì mới hiển thị nội dung chi tiết.
- **Giữ nguyên nút Citation xanh cũ:** Chỉ ẩn phần nội dung trắng của trích dẫn mặc định. Khi click vào mới bung ra cho gọn gàng.
- **Loại bỏ hiển thị "Chức danh":** Thay thế toàn bộ các chức danh cũ thành **Title (Tiêu đề) của điều luật được trích dẫn** từ văn bản pháp lý.
- **Cấu trúc khi click mở rộng trích dẫn:**
  1. Nội dung chi tiết văn bản pháp lý.
  2. Phân tích rủi ro.
  3. Gợi ý sửa đổi là citation (chỉ lấy **3 citation tốt nhất**).
- **Đưa Phân Tích Rủi Ro Cao Lên Đầu Trang:**
  - Kết quả phân tích ở đầu trang (dưới 3 thẻ Rủi ro, Cần đánh giá, An toàn) sẽ hiển thị ngay danh sách **Cảnh báo rủi ro cao** để người dùng đập mắt vào thấy ngay.
  - Phân chia các đề xuất sửa đổi và mức độ rủi ro vào từng điều khoản cụ thể.
- **Đồng bộ hóa wobbly:** Chuyển tất cả các khung file trong danh sách kết quả phân tích thành kiểu khung **wobbly** lượn sóng.

### 2.2. Đồng Bộ Hóa Phong Cách Wobbly Cho Sidebar (`frontend/src/components/layout/sidebar.tsx`)
- **Các Thẻ Lịch Sử Rà Soát & Hỏi Đáp:** Chuyển từ viền phẳng `borderRadius: "8px"` sang viền wobbly lượn sóng (`borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px"`).
- **Các Nút Điều Hướng Sidebar:** 
  - Chuyển toàn bộ các thẻ liên kết menu (Tổng quan, Cài đặt, Nâng cấp, Đăng xuất) sang phong cách wobbly.
  - Thiết kế bo góc đặc biệt cho các nút phân tách (Split Button - liên kết và nút Chevron mở rộng lịch sử) để khi ghép lại tạo thành một khối wobbly hoàn chỉnh:
    - **Nút liên kết bên trái:** `borderRadius: "255px 15px 15px 255px / 15px 225px 225px 15px"`
    - **Nút mũi tên bên phải:** `borderRadius: "15px 255px 255px 15px / 225px 15px 15px 225px"`

### 2.3. Cải Tiến Trang "Hỏi Đáp Pháp Lý" (`frontend/src/app/(app)/legal-qa/page.tsx` & `chat-bubble.tsx`)
- **Cập Nhật Câu Hỏi Mẫu:**
  - Thay đổi 3 câu hỏi mẫu ban đầu liên quan tới Luật Doanh nghiệp thành 2 câu hỏi mẫu thực tế mới theo yêu cầu:
    1. **"Lương tối thiểu vùng I"**
    2. **"Nội dung điều 1 bộ luật Lao động"**
- **Giữ vững style Wobbly:** Các nút câu hỏi mẫu, ô nhập liệu (Input Bar), bong bóng chat (Chat Bubbles) và các thẻ tài liệu trích dẫn khi mở rộng đều đã có thiết kế wobbly thống nhất.

---

## 3. Trạng Thái Hiện Tại Của Mã Nguồn
- Toàn bộ các thay đổi mới nhất đã được **commit** và **push** thành công lên nhánh **`cuong-T2.4`** của Github.
- Ứng dụng đã chạy và biên dịch mượt mà trên môi trường Next.js Turbopack (`npm run dev`).
