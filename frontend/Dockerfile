# syntax=docker/dockerfile:1.7

# --- build the static bundle ---------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Install from the lockfile so the image matches what was tested.
COPY package.json package-lock.json ./

# See backend/Dockerfile: `extra_ca` is an optional PEM bundle for networks
# behind a TLS-inspecting proxy, ignored when absent.
RUN --mount=type=secret,id=extra_ca,target=/tmp/extra-ca.crt,required=false \
    if grep -q "BEGIN CERTIFICATE" /tmp/extra-ca.crt 2>/dev/null; then export NODE_EXTRA_CA_CERTS=/tmp/extra-ca.crt; fi; \
    npm ci

COPY . .
RUN npm run build

# --- serve it, and proxy /api to the backend -----------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --spider -q http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
