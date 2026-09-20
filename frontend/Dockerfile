# Targets:
#   dev   Vite dev server with the /api proxy on :5173 (what docker-compose.yml uses)
#   prod  static build served on :4173 (put a reverse proxy in front for /api and TLS)
FROM node:22-alpine AS base
WORKDIR /app
RUN npm install -g pnpm@12.4.2
# lockfile first, so the dependency layer is cached and installs are reproducible
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .

FROM base AS dev
EXPOSE 5173
CMD ["pnpm", "exec", "vite", "--host", "0.0.0.0"]

FROM base AS build
RUN pnpm build

FROM node:22-alpine AS prod
WORKDIR /app
RUN npm install -g serve@14.2.4
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173"]
