# Bước 1: Build Image
FROM node:20-alpine AS base

# Cài đặt các thư viện cần thiết cho alpine
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Khởi tạo stage deps để cài đặt dependencies
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# Khởi tạo stage builder để build ứng dụng
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build ứng dụng (Next.js config cần có output: "standalone")
RUN npm run build

# Khởi tạo stage runner để chạy ứng dụng trong môi trường production
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

# Tạo user không có quyền root để tăng cường bảo mật
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy thư mục public
COPY --from=builder /app/public ./public

# Set quyền đúng cho thư mục .next
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Copy output standalone
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Chạy Next.js qua file server.js sinh ra từ chế độ standalone
CMD ["node", "server.js"]
