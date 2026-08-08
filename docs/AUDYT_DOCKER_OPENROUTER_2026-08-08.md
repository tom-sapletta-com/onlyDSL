# Audyt uruchomienia Docker i OpenRouter

Data testu: 2026-08-08 (Europe/Warsaw)  
Wersja aplikacji w bieżącym drzewie: 0.0.5  
Commit bazowy: `45c6031`

## Podsumowanie

Projekt działa jako lokalny proof of concept na backendzie `demo`, ale domyślne uruchomienie Compose nie jest odporne na typowe kolizje portów i nie potwierdza deklarowanej integracji aplikacji WWW z NATS/PostgreSQL. Rzeczywisty test OpenRouter na modelu `~openai/gpt-latest` połączył się z dostawcą i otrzymał odpowiedzi, lecz wszystkie trzy próby pierwszego etapu zostały poprawnie odrzucone przez walidator TwinDSL. Model generował segment URI `command` zamiast kanonicznego `commands`.

Ocena ogólna: **dobry, fail-closed POC kontraktów DSL/IFURI, jeszcze nie gotowy do wdrożenia produkcyjnego**.

## Aktualizacja po wdrożeniu poprawek

Po pierwotnym audycie uparametryzowano porty i bind do `127.0.0.1`, ograniczono kontekst obrazu, naprawiono `PYTHONPATH` integracji oraz dodano healthchecki. Profil `onlydsl-evolution` jest obecnie uruchomiony w trybie `observe`: `live-app` jest healthy pod `127.0.0.1:18787`, kolejka aktywna jest pusta, a agent ma skonfigurowany OpenRouter (`qwen/qwen3-coder-next`, klucz obecny, bez ujawnienia wartości).

Pętla napraw została przebudowana według warstw operacyjnych Subactor. AQL jest jedynym źródłem uprawnień, OQL nie zawiera transportu, URI pochodzą wyłącznie z systemowego process pack, EQL/DOQL są read-only, a wynik wiąże Process Envelope v2 i receipt SODL. Wszystkie cztery pliki process pack przechodzą oryginalne JSON Schema z projektu Subactor. Model nie może generować wykonywanych poleceń, wybierać URI/vault ani modyfikować kontraktu, process pack, dziennika audytowego i kernela governance.

Aktualny zestaw lokalny: **76/76 testów onlyDSL PASS** oraz **79/79 testów twin-dsl PASS**. Natywna paczka TestQL ma `66 PASS, 1 SKIP`; odbiór startup onlyDSL przechodzi `18/18`, a Digital Twin `20/21`. Jedyny czerwony warunek jest oczekiwany: TestQL potwierdza `iteration.validation.ok=false`, ponieważ kandydat ma rzeczywisty `GEOMETRY_REFERENCE_EXTENT_DRIFT` (14 mm ze SCAD wobec 18 mm z referencyjnego STEP/GLB). Dashboard twin udostępnia append-only event log i dokumenty DSL przez `/api/events` oraz `/api/dsl`; pełny `TestQLDSL` jest wejściem następnej iteracji jako tekst. Widok dashboardu jest także osadzony read-only w głównym UI na porcie 18787. Status pokazuje wersję wydania, wersję schematu i rewizję TwinDSL oraz czas i numer ostatniej iteracji naprawczej. Deterministyczny katalog diagnostyczny rozróżnia bezpieczne patche od `defer` i `manual`, dzięki czemu odmowa AQL, limit autonomii, konflikt dowodów lub timeout nie uruchamiają nieuzasadnionej zmiany przez LLM. Historyczne wyniki poniżej pozostają zapisane jako stan zastany z chwili pierwszego audytu.

## Zakres i wyniki testów

### 1. Domyślny Docker Compose

Polecenie:

```bash
docker compose up -d --build nats postgres app
```

Wynik: **FAIL**.

- obraz aplikacji zbudował się poprawnie;
- NATS wystartował;
- PostgreSQL nie wystartował, ponieważ hostowy port `5432` był już zajęty;
- hostowy port `8787` również był już zajęty, więc po rozwiązaniu pierwszej kolizji wystąpiłaby następna;
- porty `4222`, `8222`, `5432` i `8787` są wpisane na stałe w Compose.

Pierwszy build przesłał około **399,79 MB** kontekstu. Główną przyczyną jest brak `.venv/` w `.dockerignore` (lokalne środowisko ma około 438 MB). Obraz nie powinien kopiować lokalnego virtualenv.

### 2. Stos odizolowany do audytu

Do testu użyto dodatkowego override: bez publikacji portów PostgreSQL/NATS i z aplikacją pod `127.0.0.1:18787`.

Wynik: **PASS**.

| Element | Wynik |
|---|---|
| aplikacja | `Up`, odpowiedź na `http://127.0.0.1:18787/api/health` |
| PostgreSQL 17 | `healthy` |
| NATS 2.14.4 | gotowy, JetStream uruchomiony |
| backend aplikacji | `demo`, bez ruchu sieciowego do LLM |
| API twin | bootstrap r1, skan 2 źródeł, update r2, plan — PASS |

Endpoint zdrowia zwrócił `ok: true`, ale jest to kontrola płytka: raportuje stałe deklaracje i status konfiguracji LLM, nie sprawdza połączenia z PostgreSQL, NATS ani zapisu stanu.

### 3. Testy jednostkowe

Polecenie wewnątrz obrazu:

```bash
python3 -m unittest discover -s tests -v
```

Wynik: **44/44 PASS** w około 0,86 s.

Testy dobrze pokrywają parsery DSL, fail-closed boundary, IFURI, Protobuf, event store/outbox w wariancie jednostkowym, parity Python/Node/PHP oraz konfigurację klienta OpenRouter z mockiem.

### 4. Integracja NATS/PostgreSQL/IFURI

Udokumentowane polecenie:

```bash
docker compose run --rm integration
```

Wynik: **FAIL przed rozpoczęciem testu**:

```text
ModuleNotFoundError: No module named 'boundary'
```

Przyczyna: `python3 scripts/docker_integration.py` ustawia `scripts/` jako pierwszą ścieżkę modułów, a skrypt — w odróżnieniu od `openrouter_smoke.py` — nie dodaje katalogu `/app` do `sys.path`.

Po diagnostycznym obejściu:

```bash
PYTHONPATH=/app python3 scripts/docker_integration.py
```

wynik był **PASS**:

- Core NATS request/reply przez logiczny IFURI;
- NATS 2.14.4 i JetStream;
- zapis eventu w PostgreSQL, wersja agregatu `1`;
- atomowy event + outbox;
- publikacja outbox i `pending: 0`;
- replay oraz dekodowanie Protobuf;
- LLM gateway w trybie `demo` przez `inproc`;
- TwinDSL r1 → r2, zachowany fingerprint, 3 źródła;
- BuildPlanDSL wygenerowany.

Całe polecenie trwało około **440 s**, mimo krótkiej właściwej pracy. Należy zmierzyć etapy i znaleźć długie oczekiwanie podczas zamykania NATS/subskrypcji albo timeoutów. Test integracyjny powinien mieć jawny limit czasu i drukować czasy etapów.

### 5. Rzeczywisty OpenRouter

Polecenie:

```bash
docker compose --profile llm run --rm openrouter-smoke
```

Zaobserwowana konfiguracja, bez ujawniania klucza:

- provider: `openrouter`;
- endpoint: `https://openrouter.ai/api/v1`;
- klucz: obecny;
- model: `~openai/gpt-latest`;
- nagłówki atrybucji: `HTTP-Referer`, `X-OpenRouter-Title`.

Wynik: **FAIL na etapie bootstrap po 3 odpowiedziach modelu**.

Końcowy błąd:

```text
LLM failed twindsl validation after 3 attempt(s):
capability convert_user_intent URI invalid: invalid kind 'command';
capability evolve_from_markdown URI invalid: invalid kind 'command'
```

Wnioski:

- sieć, autoryzacja i wywołanie modelu działają;
- model zwraca treść, więc nie był to timeout ani błąd klucza;
- walidator działa prawidłowo i nie przepuszcza niekanonicznego IFURI;
- pętla naprawcza nie zdołała naprawić banalnej różnicy `command`/`commands`;
- test nie dotarł do etapów update i plan;
- skrypt nie drukuje `usage`, liczby tokenów, czasu poszczególnych wywołań ani kosztu.

W `.env` ustawiono `LLM_MODEL=openrouter/qwen/qwen3-coder-next`, ale Compose przekazuje osobno `OPENROUTER_MODEL` i w teście wykorzystał domyślne `~openai/gpt-latest`. Nazwy zmiennych i format identyfikatora modelu są niespójne. Zwykła usługa `app` nadal działa z `LLM_BACKEND=demo`, ponieważ nie ustawiono jej jawnie na `openrouter`.

## Co jest koncepcyjnie poprawne

### Ścisłe odrzucanie niepoprawnego wyniku LLM

Najlepszym elementem projektu jest zasada fail-closed. Wynik modelu musi być pojedynczym blokiem oczekiwanego DSL, przejść parser oraz walidację semantyczną. Realny test OpenRouter potwierdził, że błędny wynik nie przedostał się do domeny.

### Logiczne IFURI oddzielone od transportu

Kod domenowy używa logicznych adresów, a manifest wybiera `inproc` lub NATS. Integracja potwierdziła rozwiązywanie parametrów URI i request/reply bez wpisywania hosta/portu do domeny. To dobre rozdzielenie odpowiedzialności.

### Protobuf bez sztucznego uzależnienia od gRPC

`IfEnvelope` oraz `DslDocument` pełnią rolę kontraktu przewodowego, a transport pozostaje wymienny. Jest to sensowne dla NATS i lokalnego runtime.

### CQRS/Event Sourcing z transactional outbox

Sam wzorzec jest poprawny: PostgreSQL jest źródłem prawdy dla eventu, event i rekord outbox powstają w jednej transakcji, a publikacja do JetStream następuje po commit. Test integracyjny potwierdził ten przepływ.

### Pochodzenie źródeł

Stabilne identyfikatory dokumentów i SHA-256 umożliwiają śledzenie dowodów. Walidator realnego update sprawdza, czy LLM nie wymyślił nieznanego źródła i czy digest odpowiada bieżącemu SourceIndexDSL.

### Ochrona sekretu na poziomie repozytorium i API

`.env` jest wykluczony przez `.gitignore` i `.dockerignore`, a endpoint statusu zwraca tylko informację o obecności klucza. To właściwe minimum dla środowiska developerskiego.

## Kwestie koncepcyjne tworzące problemy

### 1. Deklarowana architektura nie jest architekturą serwera WWW

To najważniejsza rozbieżność. `server.py` tworzy wyłącznie `InProcessTransport`, a stan twin zapisuje przez plikowy `TwinStore`. Zmienne `POSTGRES_DSN`, `NATS_HOST` i `NATS_PORT` nie są wykorzystywane przez ścieżkę webową. NATS i PostgreSQL działają obok aplikacji i są używane przez osobny test integracyjny, ale nie przez główny workflow UI/API.

W efekcie komunikaty `/api/health` takie jak `cqrs_es: true` mogą sugerować więcej niż faktycznie sprawdzają. Trzeba albo podłączyć web runtime do Postgres/NATS/outbox, albo jawnie opisać aplikację jako plikowy demo adapter i rozdzielić profile `demo`/`production`.

### 2. Fingerprint nie gwarantuje zachowania semantyki intencji

Niezmienny hash dowodzi tylko, że pole hash nie zostało zmienione. Update może zmienić `INTENT_SUMMARY`, cele, treść istniejącego invariant albo reguły `EVOLUTION`, zachowując ten sam fingerprint. Walidator wymaga zachowania identyfikatora invariant, ale nie jego asercji.

Potrzebne są porównania poprzedniej i nowej wersji: niezmienność oryginalnego SourceDSL, kontrolowane zmiany celów, ochrona treści invariantów oraz polityka dozwolonych zmian zamiast samej obecności identyfikatorów.

### 3. „DSL-only” jest granicą składniową, nie ochroną przed prompt injection

Surowy tekst użytkownika i zawartość Markdown nadal trafiają do modelu, tylko jako wartości `PAYLOAD`, `PARAGRAPH`, `BULLET` lub `CODE`. Typowane opakowanie poprawia walidowalność i provenance, ale nie sprawia, że zawartość staje się zaufana. Instrukcja umieszczona w dokumencie nadal może wpływać na model.

Należy dodać poziomy zaufania źródeł, reguły pierwszeństwa, jawne oznaczenie danych jako nieinstrukcyjnych, testy prompt injection i walidację semantyczną zmian względem polityki domenowej.

### 4. BuildPlanDSL ma zbyt płytką walidację

Walidator sprawdza głównie envelope, obecność dowolnego `FROM_REVISION`, przynajmniej jednej fazy i składnię znalezionych URI. Nie parsuje pełnej struktury bloków, nie wymaga pól taska, nie porównuje `FROM_REVISION` z aktualnym twin i nie sprawdza evidence względem źródeł twin. Niepoprawny albo pusty plan może przejść kontrolę.

### 5. SourceIndexDSL nie jest w pełni deterministyczny

Dokument zawiera bieżące `GENERATED_AT`, więc dwa skany identycznych plików dają różne bajty i różny prompt. Deterministyczne są kolejność, identyfikatory i hashe źródeł, ale nie cały indeks. Jeśli wymagana jest reprodukowalność, timestamp powinien być metadanym poza dokumentem haszowanym/promptem albo powinien pochodzić z wejścia.

### 6. Plikowy TwinStore nie jest bezpieczny przy współbieżności

Serwer używa `ThreadingHTTPServer`, a store nie ma blokady ani transakcji obejmującej odczyt poprzedniej rewizji, zapis historii i podmianę current. Dwa równoległe update mogą oba zaakceptować tę samą następną rewizję, a nazwa historii z dokładnością do sekundy może się zderzyć. `reset_current()` usuwa tylko current, pozostawiając historię różnych intencji w jednym katalogu.

### 7. Publiczne porty i brak zabezpieczeń

Domyślny Compose publikuje aplikację, PostgreSQL i NATS na wszystkich interfejsach. PostgreSQL ma stałe dane `ifuri/ifuri`, NATS nie ma autoryzacji, a API nie ma uwierzytelnienia. Endpointy pozwalają resetować stan i wywoływać płatny LLM. Jest to akceptowalne wyłącznie jako lokalne laboratorium.

### 8. Sekret jest przekazywany jako zwykła zmienna środowiskowa kontenera

Repozytorium nie ujawnia klucza, ale Compose wstawia go do `environment`, więc może być widoczny przez inspekcję kontenera dla użytkownika z dostępem do Dockera. Dla wdrożenia należy użyć secret managera/Docker secrets i nie kopiować całego repozytorium do obrazu.

## Priorytet napraw

### P0 — blokery poprawnego testowania i bezpiecznego uruchomienia

1. Naprawić import w `scripts/docker_integration.py` tak samo jak w `openrouter_smoke.py` albo uruchamiać skrypty jako moduły pakietu.
2. Uparametryzować bind portów (`APP_PORT`, `POSTGRES_PORT`, `NATS_PORT`, `NATS_MONITOR_PORT`) i domyślnie wiązać je do `127.0.0.1`; pozwolić wyłączyć publikację baz i NATS.
3. Dodać `.venv/`, `.pytest_cache/`, `.idea/` i lokalne artefakty do `.dockerignore`; budować obraz z jawnej listy plików zamiast `COPY . .`.
4. Ujednolicić `OPENROUTER_MODEL`/`LLM_MODEL`, podawać jawny model do smoke i logować model, token usage, czas oraz liczbę repair attempts.
5. Rozszerzyć `schemadsl` o zamkniętą definicję `kind = commands | queries | events | artifacts | streams` i kanoniczne przykłady. Dodać test regresji realnego błędu `command`/`commands`.

### P1 — zgodność architektury z deklaracjami

1. Podłączyć workflow web do Postgres event store/outbox i NATS albo obniżyć deklaracje health/README do rzeczywistego wariantu demo.
2. Dodać healthcheck kontenera aplikacji oraz readiness zależne od faktycznie wymaganych usług; użyć `depends_on: condition: service_healthy` dla Postgres.
3. Zastąpić plikowy store transakcyjnym repozytorium lub dodać blokady, optimistic concurrency i rozdzielenie historii według twin/intent.
4. Wzmocnić walidację ewolucji: niezmienne źródło intencji, treść invariantów i kontrola zmian celów/zakazów.
5. Napisać pełny parser i walidator BuildPlanDSL z kontrolą rewizji i provenance.

### P2 — produkcja i obserwowalność

1. Dodać uwierzytelnienie/autoryzację API, limity rozmiaru body i rate limiting dla płatnych operacji LLM.
2. Wyłączyć publiczne porty bazy/NATS, włączyć credentials/TLS i użyć secrets.
3. Dodać metryki czasu/kosztu/tokenów LLM, rozróżnienie błędów provider/validation i kontrolowany retry/backoff.
4. Dodać timeout dla testu integracyjnego oraz telemetrykę etapów, aby wyjaśnić około 440 s czasu wykonania.
5. Dodać testy konkurencji, restartu, utraty NATS, niedostępności PostgreSQL, prompt injection i zmian złośliwego źródła.

## Kryteria ponownego odbioru

Projekt można uznać za poprawnie uruchomiony po spełnieniu łącznie:

1. `docker compose up -d` działa bez lokalnych zmian albo porty można skonfigurować w `.env`.
2. Wszystkie usługi mają health/readiness, a health aplikacji sprawdza zależności używane przez jej workflow.
3. Udokumentowane `docker compose run --rm integration` przechodzi bez `PYTHONPATH` workaround i kończy się w przewidywalnym czasie.
4. Pełny smoke OpenRouter drukuje `BOOTSTRAP_OK`, `UPDATE_OK`, `PLAN_OK`, `OPENROUTER_SMOKE_PASS` dla jawnie wybranego modelu.
5. Workflow web używa tej samej ścieżki persistence/transport, którą deklaruje architektura, albo dokumentacja jasno oznacza różnicę między demo a production.
6. Żaden sekret nie znajduje się w obrazie, logach, raporcie ani odpowiedzi API.
