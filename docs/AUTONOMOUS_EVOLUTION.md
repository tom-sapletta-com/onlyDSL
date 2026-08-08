# Autonomiczna ewolucja zgodna z warstwami Subactor

Profil Docker `evolution` uruchamia aplikację pod nadzorem procesu reloadującego oraz osobnego agenta naprawczego. Implementacja korzysta z modelu opisanego w `FOUNDER_OPERATIONAL_DSL_LAYERS.md` projektu Subactor.

## Granice odpowiedzialności

Przepływ ma postać:

```text
GuidanceDSL + IncidentDSL + CodeDSL
  -> systemowy katalog błędów tworzy DiagnosticDSL i wybiera patch/defer/manual
  -> LLM proponuje wyłącznie PatchDSL
  -> hash propozycji i prior policy grant
  -> DOQL: odczyt hashy i stanu, bez sekretów
  -> AQL: jedyne źródło uprawnień
  -> OQL: abstrakcyjna operacja
  -> systemowy URI Process: dokładna, wcześniej zdefiniowana trasa
  -> preflight i zastosowanie patcha
  -> stały systemowy test runner + reload
  -> niezależny EQL health read-back
  -> SODL receipt albo rollback
```

Model nie może nadać sobie uprawnień, utworzyć URI, wybrać transportu lub wpisu vault ani oznaczyć własnej odpowiedzi jako zaakceptowanej bądź zweryfikowanej. Nie ma też parsera ani executora poleceń powstałych w odpowiedzi LLM. `git apply`, testy i healthcheck są stałymi operacjami systemu.

## Diagnostyka kodów błędów

Każdy nowy IncidentDSL jest natychmiast klasyfikowany przez systemowy katalog w `diagnostics.py`. Wynik jest zapisywany jako DiagnosticDSL w `runtime/evolution/diagnostics/` i zawiera stabilny `ERROR_CODE`, kategorię, poziom pewności, przyczynę, cel naprawy, kroki rozwiązania i niezależne warunki `VERIFY`. Sugerowana para OQL/URI jest informacyjna (`NOTE suggestion_is_not_authority`); właściwa decyzja nadal pochodzi wyłącznie z AQL i process packa.

Katalog rozpoznaje obecnie między innymi:

- `AUTONOMY_RATE_LIMIT_EXCEEDED`, `ITERATION_POLICY_DENIED`;
- `AQL_AUTHORITY_DENIED`;
- `PYTHON_IMPORT_ERROR`, `PYTHON_MODULE_NOT_FOUND`;
- `TESTQL_ASSERTION_FAILED`, `JSON_DECODE_ERROR`;
- `HTTP_NOT_FOUND`, `HTTP_SERVER_ERROR`;
- `CONNECTION_REFUSED`, `OPERATION_TIMEOUT`;
- `PATCH_BASE_STALE` oraz kontrolowany fallback `UNCLASSIFIED_RUNTIME_ERROR`.

Akcja `patch` dołącza DiagnosticDSL do typowanego wejścia LLM. `defer` przenosi incydent do `deferred/` bez wywołania modelu (np. limit autonomii, timeout, niedostępna usługa). `manual` zatrzymuje automatyczny patch przy odmowie AQL lub bramki polityki. Mechanizm diagnostyczny jest częścią chronionego kernela i nie może być zmieniony przez PatchDSL modelu.

Odczyt ostatnich diagnoz:

```bash
curl -fsS 'http://127.0.0.1:18787/api/evolution/diagnostics?limit=20' | python3 -m json.tool
```

Źródła polityki:

- `config/contracts/evolution-agent.contract.aql` — kontrakt `aql:contract/v1`;
- `config/process-packs/live-evolution/process.v1.json` — policy/approval/idempotency;
- `operations.v1.oql.json` — transport-free OQL;
- `recipe.v1.urirun.json` — systemowe URI Process;
- `expectations.v1.eql.json` — tylko odczyt i weryfikacja.

Cztery dokumenty process pack przechodzą bezpośrednią walidację schematami JSON projektu Subactor. Kontrakt AQL jest montowany w kontenerze agenta read-only. Sam agent dodatkowo odrzuca modyfikacje `config/contracts/`, `config/process-packs/`, historii `runtime/evolution/`, `.git/`, `state/`, wartości sekretów oraz minimalnego kernela governance (`aql.py`, `governance.py`, `patchdsl.py`, `scripts/autonomous_repair.py`).

## Zakres nadanych uprawnień

Domyślny kontrakt developerski ma szerokie granty `ALLOW OQL *` oraz wildcardy dla systemowych tras ograniczonych do `repo://workspace/*`, `process://workspace/*`, health aplikacji i `vault://workspace/secret/*`. Pozwala to testować wszystkie zarejestrowane operacje projektu bez każdorazowej edycji AQL. Nie zezwala na `shell://`, URI wskazujące poza workspace ani trasy wygenerowane przez model.

Systemowy process pack wiąże `bot:evolution-agent` z parami OQL/URI dla:

- `code.change` — kod aplikacji;
- `dependency.change` — manifesty zależności;
- `docker.change` — Dockerfile i Compose;
- `runtime.change` — pliki runtime poza dziennikiem governance;
- `evolution.change` — ewoluowalna część pętli (kolejka, supervisor i integracja aplikacji), ale nie konstytucyjny kernel AQL/executor;
- `secret.rotate` — wyłącznie niejawna referencja `secret:<id>` i systemowa trasa vault.

To nie jest allowlista w promptcie. Każdy plik PatchDSL jest klasyfikowany deterministycznie, a agent wymaga jednocześnie grantu OQL i dokładnej trasy URI. Dowolna trasa typu `shell://...`, nawet umieszczona przez model w treści, nie jest wykonywana.

Wartość sekretu nigdy nie przechodzi przez CodeDSL/PatchDSL. Zaimplementowano autoryzację rotacji dowolnej referencji `secret:<id>` w developerskim workspace, ale repozytorium nie ma jeszcze zewnętrznego konektora vault, więc faktyczna rotacja kończy się fail-closed do czasu podłączenia systemowego adaptera. Nie należy zastępować go komendą wygenerowaną przez model.

## Uruchomienie

Tryb obserwacji zapisuje guidance, incydenty i logi DSL, ale nie wywołuje LLM i nie modyfikuje kodu:

```bash
LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" \
EVOLUTION_MODE=observe \
docker compose --profile evolution up -d --build live-app evolution-agent
```

Tryb zastosowania wymaga `OPENROUTER_API_KEY` w lokalnym `.env`:

```bash
LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" \
EVOLUTION_MODE=apply EVOLUTION_ENABLED=1 \
docker compose --profile evolution up -d --build live-app evolution-agent
```

Aplikacja: `http://127.0.0.1:18787`.

Przed przejściem do `apply` należy przejrzeć `runtime/evolution/inbox/`, aby stary incydent nie uruchomił nowej mutacji.

## Sterowanie i obserwacja

Dodanie wytycznej:

```bash
curl -fsS -X POST http://127.0.0.1:18787/api/evolution/guidance \
  -H 'Content-Type: application/json' \
  --data '{"directive":"Zachowaj kompatybilność API i wykonaj minimalną naprawę.","priority":"high"}'
```

Zgłoszenie błędu:

```bash
curl -fsS -X POST http://127.0.0.1:18787/api/evolution/report \
  -H 'Content-Type: application/json' \
  --data '{"kind":"reported_bug","message":"GET /api/example zwraca 500; server.py:120","route":"/api/example"}'
```

Status pokazuje kolejkę, kontrakt AQL i granicę wykonywania:

```bash
curl -fsS http://127.0.0.1:18787/api/evolution/status
docker compose --profile evolution logs -f live-app evolution-agent
```

## Audit trail i rollback

```text
runtime/evolution/
├── guidance/     GuidanceDSL
├── inbox/        nowe IncidentDSL
├── processing/   atomowo przejęte incydenty
├── processed/    naprawy z zielonym EQL
├── failed/       odrzucenia i rollbacki
├── deferred/     retry/manual bez nieuzasadnionego patcha LLM
├── diagnostics/  kody błędów i rozwiązania DiagnosticDSL
├── patches/      odpowiedzi PatchDSL
├── envelopes/    Process Envelope v2 z hashami i decyzją AQL
├── receipts/     receipt SODL po niezależnej weryfikacji
├── testql/       startup results JSON + TestQLDSL z hashami
├── backups/      kopie bajt-w-bajt
└── events/       append-only EventDSL
```

Status `verified` powstaje dopiero po testach i health read-back. Niepowodzenie przywraca backup i ponownie sprawdza zdrowie aplikacji. Agent nie wykonuje `commit` ani `push`.

## Odbiór startowy TestQL

Jednorazowa usługa `testql-startup` używa publicznego kontraktu TestQL `testql.verification-result.v1`. Uruchamia dwa natywne scenariusze TestTOON:

- `testql/onlydsl-startup.testql.toon.yaml` — health, DSL-only, IFURI, AQL i granica wykonywania;
- `testql/digital-twin-startup.testql.toon.yaml` — `/api/state`, schemat twin/scene/iteration, walidacja iteracji i dostępność event logu pod portem 7444.

Wyniki trafiają do `runtime/evolution/testql/` równocześnie jako kanoniczny JSON TestQL oraz `TestQLDSL`. Błąd onlyDSL tworzy `IncidentDSL`, który agent może wykorzystać w następnej naprawie; odpowiadający mu `TestQLDSL` jest dołączany do typowanego pakietu naprawczego. Wynik zewnętrznego Digital Twin jest zapisywany jako obserwacja `logs/testql-verification.jsonl` oraz pełny `logs/testql-latest.testqldsl` w projekcie twin. Skaner twin traktuje rozszerzenie `.testqldsl` jako tekst, dzięki czemu następna iteracja pobiera zarówno pola obserwacji, jak i kompletny dowód DSL zamiast binarnego placeholdera.

Dashboard Digital Twin pod `http://127.0.0.1:7444/` pokazuje panel **DSL & iteration log**. Ostatnie zdarzenia append-only są dostępne pod `/api/events`, a bieżące dokumenty obserwacji, obliczeń, ulepszeń i TestQLDSL pod `/api/dsl`.

Ręczny odbiór:

```bash
docker compose -p onlydsl-evolution --profile evolution run --rm --no-deps testql-startup
```

Runner ma osobny, mały obraz `Dockerfile.testql`. Używa TestQL `1.2.66` i tylko zależności potrzebnych do scenariuszy API; opcjonalne GUI, Playwright, LLM i autofix nie są instalowane. Adres i katalog zewnętrznego twin można zmienić przez `TESTQL_TWIN_URL` oraz `TESTQL_TWIN_PROJECT_DIR`.

Lokalny checkout `/home/tom/github/oqlos/testql` ponownie obsługuje natywny `python -m testql run-ir`: naprawiono import `TestToonAdapter`, przywrócono wyzerowane moduły interpretera oraz poprawiono mapowanie skróconych asercji API do pola IR `data` wraz z typowaniem `true/false`. Jego zestaw rdzeniowy przechodzi `1459 passed, 57 skipped`. Scenariusz onlyDSL uruchomiony bezpośrednio przez lokalny checkout przechodzi `6/6`; scenariusz twin poprawnie raportuje bieżący czerwony stan runtime jako `6/7`, zamiast błędu parsera.

Izolowany obraz startowy nadal instaluje opublikowany wheel `testql==1.2.66`, aby build Compose nie zależał od absolutnej ścieżki repozytorium znajdującego się poza kontekstem Dockera. Nie używa własnego formatu wyniku: scenariusze pozostają natywnym TestTOON, a zapis korzysta z publicznego kontraktu `testql.verification-result.v1`. Po opublikowaniu poprawionej wersji TestQL pin obrazu można podnieść bez zmiany scenariuszy ani DSL wyniku.

Natywny odbiór lokalnym checkoutem:

```bash
cd /home/tom/github/oqlos/testql
.venv/bin/python -m testql run-ir \
  /home/tom/github/tom-sapletta-com/onlyDSL/testql/onlydsl-startup.testql.toon.yaml \
  --api-url http://127.0.0.1:18787 --output json
```

## Znane braki

- Brak systemowego konektora vault wykonującego zatwierdzoną rotację sekretu.
- Limity `LIMIT STEPS` i `LIMIT EXECUTIONS` są zapisane w kontrakcie, ale licznik trwały nie jest jeszcze egzekwowany.
- Process Envelope zapisuje prior policy grant związany z hashem propozycji; osobna ścieżka akceptacji człowieka per patch nie ma jeszcze API/UI.
- Test runner jest celowo stały. Rozszerzanie zestawu testów wymaga zmiany systemowego process pack, nie odpowiedzi modelu.

Zatrzymanie:

```bash
docker compose --profile evolution stop evolution-agent live-app
```
