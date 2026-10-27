FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . ./
# Next.js inlines NEXT_PUBLIC_* at build time, so the API base URL must be a
# build ARG (a runtime `environment:` in compose has no effect). Default points
# at the compose service DNS name so server-side fetches reach the API container.
ARG NEXT_PUBLIC_API_URL=http://api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
