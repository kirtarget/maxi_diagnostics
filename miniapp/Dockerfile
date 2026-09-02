FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS dependencies
WORKDIR /app/miniapp
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci

FROM dependencies AS licenses
COPY miniapp/scripts /app/miniapp/scripts
RUN node scripts/collect-production-licenses.mjs /app/licenses/THIRD_PARTY_NODE_LICENSES.txt

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS builder
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=dependencies /app/miniapp/node_modules /app/miniapp/node_modules
COPY miniapp /app/miniapp
COPY school/brand.json school/links.json /app/school/
COPY school/assets /app/school/assets
WORKDIR /app/miniapp
RUN npm run build

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
COPY --chown=node:node --from=builder /app/miniapp/.next/standalone ./
COPY --chown=node:node --from=builder /app/miniapp/.next/static /app/miniapp/.next/static
COPY --chown=node:node --from=builder /app/miniapp/public /app/miniapp/public
COPY --chown=node:node LICENSE THIRD_PARTY_NOTICES.md third_party_licenses /app/licenses/
COPY --chown=node:node --from=licenses /app/licenses /app/licenses/node-runtime
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
CMD ["node", "miniapp/server.js"]
