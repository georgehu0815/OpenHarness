# --- Build stage ---
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/web/package*.json ./
RUN npm ci
COPY frontend/web/ .
RUN npm run build

# --- Serve stage ---
FROM nginx:alpine
# Remove default config
RUN rm /etc/nginx/conf.d/default.conf
# Copy our config — uses envsubst variables (nginx:alpine processes templates/ at startup)
COPY frontend/web/nginx.conf /etc/nginx/templates/default.conf.template
# Copy built SPA
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
