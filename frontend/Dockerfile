FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Production build, baked into the image at build time - "next dev" is
# meant for live local editing (slower, includes hot-reload overhead,
# more verbose errors), not a long-running autonomous deployment.
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
