export type IfUriKind = 'commands'|'queries'|'events'|'artifacts'|'streams';
export interface IfUri { boundedContext:string; entity:string; identity:string; kind:IfUriKind; operation:string }
const prefixes: Record<IfUriKind,string> = {commands:'cmd',queries:'qry',events:'evt',artifacts:'art',streams:'str'};
const segment=/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/;
export function parseIfUri(raw:string):IfUri {
  const u=new URL(raw);
  if(u.protocol!=='ifuri:' || u.username || u.password || u.port || u.search || u.hash) throw new Error('invalid IFURI placement/scheme');
  const p=u.pathname.split('/').filter(Boolean);
  if(p.length!==4) throw new Error('expected 4 path segments');
  const [entity,identity,kindRaw,operation]=p;
  if(!segment.test(u.hostname)||!segment.test(entity)||!segment.test(identity)||!segment.test(operation)) throw new Error('invalid segment');
  if(!(kindRaw in prefixes)) throw new Error('invalid kind');
  return {boundedContext:u.hostname,entity,identity,kind:kindRaw as IfUriKind,operation};
}
export function toNatsSubject(raw:string):string {
  const x=parseIfUri(raw);
  return `ifuri.${prefixes[x.kind]}.${x.boundedContext}.${x.entity}.${x.identity}.${x.operation}`;
}
