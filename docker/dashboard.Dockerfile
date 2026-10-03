FROM node:22-slim
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY dashboard/ .
EXPOSE 5173
CMD ["npm", "run", "dev"]
