<?php
function parse_ifuri(string $raw): array {
    $u = parse_url($raw);
    if ($u === false || ($u['scheme'] ?? '') !== 'ifuri') throw new Exception('scheme must be ifuri');
    foreach (['user','pass','port','query','fragment'] as $k) if (isset($u[$k])) throw new Exception('placement fields forbidden');
    $host = strtolower($u['host'] ?? '');
    $parts = array_values(array_filter(explode('/', $u['path'] ?? ''), fn($x)=>$x!==''));
    if (count($parts) !== 4) throw new Exception('expected 4 path segments');
    [$entity,$identity,$kind,$operation] = $parts;
    $re='/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/';
    foreach ([$host,$entity,$identity,$operation] as $x) if (!preg_match($re,$x)) throw new Exception('invalid segment');
    $prefixes=['commands'=>'cmd','queries'=>'qry','events'=>'evt','artifacts'=>'art','streams'=>'str'];
    if (!isset($prefixes[$kind])) throw new Exception('invalid kind');
    return ['bounded_context'=>$host,'entity'=>$entity,'identity'=>$identity,'kind'=>$kind,'operation'=>$operation];
}
function canonical_ifuri(string $raw): string {
    $x=parse_ifuri($raw);
    return "ifuri://{$x['bounded_context']}/{$x['entity']}/{$x['identity']}/{$x['kind']}/{$x['operation']}";
}
function nats_subject(string $raw): string {
    $x=parse_ifuri($raw); $p=['commands'=>'cmd','queries'=>'qry','events'=>'evt','artifacts'=>'art','streams'=>'str'][$x['kind']];
    return "ifuri.$p.{$x['bounded_context']}.{$x['entity']}.{$x['identity']}.{$x['operation']}";
}
if (PHP_SAPI === 'cli' && realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    $raw=$argv[1] ?? '';
    echo json_encode(['canonical'=>canonical_ifuri($raw),'subject'=>nats_subject($raw)], JSON_UNESCAPED_SLASHES).PHP_EOL;
}
?>
