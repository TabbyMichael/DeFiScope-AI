# DeFiScope AI - web image (multi-stage Next.js standalone, non-root, healthchecked).

# --- Deps stage: install exact dependencies (cached on package.json changes) --
# Alpine (musl) base: Docker Scout reports 0C/10H vs node:22-slim's 0C/18H/39L.
# Next.js ships musl builds of its SWC native compiler (@next/swc-linux-x64-musl),
# which npm selects automatically, so the standalone build works unchanged.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# --- Build stage: compile the standalone server -------------------------------
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . ./
# Next.js inlines NEXT_PUBLIC_* at build time, so the API base URL must be a
# build ARG (a runtime `environment:` in compose has no effect). Default points
# at the compose service DNS name so server-side fetches reach the API container.
ARG NEXT_PUBLIC_API_URL=http://api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Browser-reachable API URL for the docs link. The internal `api:8000` host is
# unresolvable from the user's browser, so this is the host-published address
# (compose maps the API to http://localhost:3646). Falls back to the server URL
# when unset (local dev).
ARG NEXT_PUBLIC_API_PUBLIC_URL=http://localhost:3646
ENV NEXT_PUBLIC_API_PUBLIC_URL=$NEXT_PUBLIC_API_PUBLIC_URL
# Browser-reachable WebSocket base for streamed chat tokens (roadmap #8). Also
# build-time only (inlined into the client bundle). Defaults to the host-published
# API port so the browser opens the chat socket directly against the api service.
ARG NEXT_PUBLIC_API_WS_URL=ws://localhost:3646
ENV NEXT_PUBLIC_API_WS_URL=$NEXT_PUBLIC_API_WS_URL
# One-click demo sign-in buttons on /login. Build-time only (client bundle), so
# a production image must NOT pass this. The password is likewise public by
# design: the demo accounts are a tour, not a secret.
ARG NEXT_PUBLIC_AUTH_DEMO=
ENV NEXT_PUBLIC_AUTH_DEMO=$NEXT_PUBLIC_AUTH_DEMO
ARG NEXT_PUBLIC_AUTH_DEMO_PASSWORD=defiscope-demo
ENV NEXT_PUBLIC_AUTH_DEMO_PASSWORD=$NEXT_PUBLIC_AUTH_DEMO_PASSWORD
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- Runtime stage: minimal, non-root, standalone server only -----------------
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `node` user (uid 1000) ships with the base image - run as it, no root.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000

# Liveness probe: confirm the standalone server is accepting connections. Any
# HTTP response counts as alive (we do not gate web health on API availability).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "require('http').get('http://127.0.0.1:3000/',r=>{r.resume();process.exit(0)}).on('error',()=>process.exit(1))"]

CMD ["node", "server.js"]
