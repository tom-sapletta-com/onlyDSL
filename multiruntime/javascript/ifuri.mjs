const kinds = new Map([
  ['commands','cmd'], ['queries','qry'], ['events','evt'], ['artifacts','art'], ['streams','str']
]);
const seg = /^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/;

export function parseIfUri(raw) {
  const u = new URL(raw);
  if (u.protocol !== 'ifuri:') throw new Error("scheme must be ifuri");
  if (u.username || u.password || u.port || u.search || u.hash) throw new Error("placement fields forbidden");
  const parts = u.pathname.split('/').filter(Boolean);
  if (parts.length !== 4) throw new Error("expected 4 path segments");
  const [entity, identity, kind, operation] = parts;
  if (!seg.test(u.hostname) || !seg.test(entity) || !seg.test(identity) || !seg.test(operation)) throw new Error("invalid segment");
  if (!kinds.has(kind)) throw new Error("invalid kind");
  return {bounded_context:u.hostname, entity, identity, kind, operation};
}

export function canonical(raw) {
  const x=parseIfUri(raw);
  return `ifuri://${x.bounded_context}/${x.entity}/${x.identity}/${x.kind}/${x.operation}`;
}

export function toNatsSubject(raw) {
  const x=parseIfUri(raw);
  return `ifuri.${kinds.get(x.kind)}.${x.bounded_context}.${x.entity}.${x.identity}.${x.operation}`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const raw=process.argv[2];
  console.log(JSON.stringify({canonical:canonical(raw),subject:toNatsSubject(raw)}));
}
