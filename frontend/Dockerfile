# ── Stage 1 : Build ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --silent

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

ARG VITE_BADGE_BASE_URL
ENV VITE_BADGE_BASE_URL=${VITE_BADGE_BASE_URL}

RUN npm run build

# ── Stage 2 : Serve ──────────────────────────────────────────
FROM nginx:1.27-alpine

ARG VERSION=dev
LABEL version=${VERSION}

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
