FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Source is overlaid at runtime via a bind mount in docker-compose.
# COPY here ensures a self-contained image when run standalone.
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
