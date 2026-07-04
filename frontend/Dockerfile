FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

# Dev-режим первого релиза (ТЗ 19.2): Vite dev-сервер на :3000.
CMD ["npm", "run", "dev"]
