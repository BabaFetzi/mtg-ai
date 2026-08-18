# ============================================================================
#  start.ps1 - Grana lokal starten: Backend + Frontend + Stripe
#
#  Aufruf in PowerShell, im Projektordner:
#
#      .\start.ps1
#
#  Beendet wird alles zusammen mit Strg + C in genau diesem Fenster.
#
#  Kommt beim ersten Versuch "die Ausfuehrung von Skripts ist auf diesem
#  System deaktiviert", dann blockiert Windows PowerShell-Skripte generell.
#  Entweder einmalig erlauben:
#
#      Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
#  oder ohne dauerhafte Aenderung nur fuer diesen einen Start:
#
#      powershell -ExecutionPolicy Bypass -File .\start.ps1
#
#  ---------------------------------------------------------------------------
#  NUR ZUM LOKALEN TESTEN. Fuer den echten Server gibt es start.sh.
#  ---------------------------------------------------------------------------
#
#  Warum ueberhaupt Stripe mitstarten
#  ----------------------------------
#  Ohne die Stripe-CLI kommt lokal KEIN Webhook an. Ein Kauf im Testmodus
#  laeuft dann bis zur Bezahlseite durch und danach passiert nichts mehr:
#  keine Premium-Freischaltung, kein Abo-Status. Das sieht wie ein Fehler in
#  Grana aus, ist aber nur ein fehlender Zusteller.
#
#  Die CLI nimmt die Ereignisse von Stripe entgegen und leitet sie an das
#  lokale Backend weiter.
#
#  Der Stolperstein, den dieses Skript aus dem Weg raeumt
#  ------------------------------------------------------
#  "stripe listen" benutzt einen EIGENEN Signaturschluessel -- einen anderen
#  als den aus dem Stripe-Dashboard. Steht in der .env der Dashboard-
#  Schluessel, scheitert lokal JEDER Webhook an der Signaturpruefung, mit
#  einer Meldung, die nach einem Programmfehler aussieht.
#
#  Deshalb holt dieses Skript den lokalen Schluessel bei der CLI ab und gibt
#  ihn dem Backend als Umgebungsvariable mit. Deine .env wird dabei NICHT
#  angefasst: python-dotenv laesst eine bereits gesetzte Umgebungsvariable
#  stehen (nachgeprueft), die Datei bleibt also fuer den echten Betrieb
#  richtig.
# ============================================================================

param(
    # Startet nichts, sondern zeigt nur, wie python, npm und stripe auf DIESEM
    # Rechner aufgeloest werden. Gedacht fuer den Fall, dass ein Start
    # scheitert: die Ausgabe sagt in einem Schritt, woran es liegt.
    [switch]$Diagnose
)

$ErrorActionPreference = 'Stop'

# PowerShell ab 7.3 behandelt JEDE Ausgabe eines externen Programms auf der
# Fehlerausgabe als abbrechenden Fehler, sobald ErrorActionPreference auf
# 'Stop' steht. pip, npm und die Stripe-CLI schreiben dort ganz normale
# Hinweise hin ("notice: A new release of pip is available") -- das Skript
# waere sonst mitten in der Einrichtung gestorben, mit einer Meldung, die wie
# ein echter Fehler aussieht. Massgeblich ist hier der Rueckgabewert
# ($LASTEXITCODE), der unten geprueft wird.
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

Set-Location -Path $PSScriptRoot

$BackendPort  = 8001
$FrontendPort = 5175
$WebhookPfad  = '/api/v1/payments/webhook'

$Prozesse = @()

function Schreib([string]$Text, [string]$Farbe = 'Gray') {
    Write-Host $Text -ForegroundColor $Farbe
}

function Titel([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 66) -ForegroundColor DarkCyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('=' * 66) -ForegroundColor DarkCyan
}

function Vorhanden([string]$Befehl) {
    $null -ne (Get-Command $Befehl -ErrorAction SilentlyContinue)
}

function StarteProgramm([string]$Befehl, [string[]]$Argumente, [string]$Verzeichnis) {
    <#
        Startet ein Programm -- auch dann, wenn es gar keine .exe ist.

        Der Grund: Mit -NoNewWindow benutzt Start-Process CreateProcess, und
        das kann NUR echte ausfuehrbare Dateien starten. Die Stripe-CLI und npm
        liegen auf Windows aber haeufig als .cmd-Zwischenstueck vor (Scoop,
        Chocolatey, npm selbst). Der Versuch endet dann mit

            %1 ist keine zulaessige Win32-Anwendung.

        -- einer Meldung, die aussieht, als waere das Programm kaputt, obwohl
        es voellig in Ordnung ist. Dieselbe Datei laesst sich naemlich ueber
        den Aufrufoperator (&) problemlos ausfuehren, weil PowerShell dort die
        Kommandozeile dazwischenschaltet.

        Genau das wird hier von Hand gemacht: .cmd und .bat laufen ueber
        cmd.exe, .ps1 ueber PowerShell, alles andere direkt.
    #>
    $gefunden = Get-Command $Befehl -ErrorAction SilentlyContinue
    if (-not $gefunden) {
        throw "Das Programm '$Befehl' wurde nicht gefunden."
    }

    $pfad = $gefunden.Source
    if (-not $pfad) { $pfad = $Befehl }
    $endung = [System.IO.Path]::GetExtension($pfad).ToLowerInvariant()

    $rest = $Argumente -join ' '

    try {
        switch ($endung) {
            { @('.cmd', '.bat') -contains $_ } {
                # Die Anfuehrungszeichen-Regeln von cmd.exe sind heikel, und
                # npm liegt oft unter "C:\Program Files\nodejs\" -- also MIT
                # Leerzeichen. Verlaesslich ist genau eine Form:
                #
                #     cmd /s /c ""C:\Pfad mit Leerzeichen\npm.cmd" run dev"
                #
                # Mit /s nimmt cmd alles zwischen dem ERSTEN und dem LETZTEN
                # Anfuehrungszeichen woertlich. Uebergeben wird das als EINE
                # Zeichenkette, weil PowerShell bei einem Array selbst noch
                # einmal Anfuehrungszeichen setzt und die Form damit zerstoert.
                return Start-Process -FilePath $env:ComSpec `
                    -ArgumentList "/s /c `"`"$pfad`" $rest`"" `
                    -WorkingDirectory $Verzeichnis -PassThru -NoNewWindow
            }
            '.ps1' {
                return Start-Process -FilePath 'powershell.exe' `
                    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$pfad`" $rest" `
                    -WorkingDirectory $Verzeichnis -PassThru -NoNewWindow
            }
            default {
                # Echte Programme kann Start-Process direkt starten. Hier ist
                # das Array richtig: es setzt Anfuehrungszeichen genau dort,
                # wo ein einzelnes Argument Leerzeichen enthaelt.
                if ($Argumente -and $Argumente.Count -gt 0) {
                    return Start-Process -FilePath $pfad -ArgumentList $Argumente `
                        -WorkingDirectory $Verzeichnis -PassThru -NoNewWindow
                }
                return Start-Process -FilePath $pfad `
                    -WorkingDirectory $Verzeichnis -PassThru -NoNewWindow
            }
        }
    } catch {
        # Mit dem aufgeloesten Pfad in der Meldung ist ein solcher Fehler beim
        # naechsten Mal in einem Schritt zu klaeren statt in dreien.
        throw ("'{0}' liess sich nicht starten. Aufgeloest zu: {1} (Endung '{2}'). Ursache: {3}" `
               -f $Befehl, $pfad, $endung, $_.Exception.Message)
    }
}

function PortBelegt([int]$Port) {
    # Get-NetTCPConnection gibt es nicht ueberall (PowerShell 5 auf aelteren
    # Systemen, PowerShell Core auf macOS). Faellt es aus, wird der Port als
    # frei behandelt -- dann meldet sich spaeter der Dienst selbst.
    try {
        $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        $false
    }
}

if ($Diagnose) {
    Titel 'Diagnose -- wie werden die Programme aufgeloest?'
    foreach ($b in @('python', 'npm', 'stripe')) {
        $g = Get-Command $b -ErrorAction SilentlyContinue
        if ($g) {
            Schreib ("{0,-8} {1,-12} {2}" -f $b, $g.CommandType, $g.Source) Green
        } else {
            Schreib ("{0,-8} NICHT GEFUNDEN" -f $b) Yellow
        }
    }
    Schreib ''
    Schreib ("PowerShell {0} auf {1}" -f $PSVersionTable.PSVersion, [System.Environment]::OSVersion.VersionString) DarkGray
    $venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    Schreib ("venv       {0}" -f $(if (Test-Path $venv) { 'vorhanden' } else { 'fehlt' })) DarkGray
    Schreib (".env       {0}" -f $(if (Test-Path '.env') { 'vorhanden' } else { 'fehlt' })) DarkGray
    exit 0
}

Titel 'Grana - lokaler Start'

# ---------------------------------------------------------------------------
# 1. Voraussetzungen
# ---------------------------------------------------------------------------
if (-not (Vorhanden 'python')) {
    Schreib '[FEHLER] Python wurde nicht gefunden.' Red
    Schreib '         Installieren von https://www.python.org/downloads/' Red
    Schreib '         WICHTIG: beim Installieren "Add Python to PATH" ankreuzen.' Red
    exit 1
}
if (-not (Vorhanden 'npm')) {
    Schreib '[FEHLER] Node.js / npm wurde nicht gefunden.' Red
    Schreib '         Installieren von https://nodejs.org/ (LTS-Version)' Red
    exit 1
}

foreach ($p in @($BackendPort, $FrontendPort)) {
    if (PortBelegt $p) {
        Schreib "[FEHLER] Port $p ist schon belegt." Red
        Schreib '         Laeuft Grana vielleicht noch in einem anderen Fenster?' Red
        Schreib "         Nachsehen mit:  Get-NetTCPConnection -LocalPort $p" Red
        exit 1
    }
}

if (-not (Test-Path '.env')) {
    Schreib '[HINWEIS] Es gibt noch keine .env -- ich lege eine aus .env.example an.' Yellow
    Copy-Item '.env.example' '.env'
    Schreib '          Die Anwendung startet damit, aber ohne Schluessel sind' Yellow
    Schreib '          KI, Mailversand und Bezahlung aus. Traeg sie in .env nach.' Yellow
}

# ---------------------------------------------------------------------------
# 2. Einmalige Einrichtung
# ---------------------------------------------------------------------------
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    Schreib '[1/3] Erstelle die Python-Umgebung (nur beim ersten Mal)...' White
    python -m venv .venv
}

Schreib '[2/3] Pruefe die Backend-Pakete...' White
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Schreib '[FEHLER] Die Backend-Pakete liessen sich nicht installieren.' Red
    exit 1
}

if (-not (Test-Path 'mtg-frontend\node_modules')) {
    Schreib '[3/3] Installiere die Frontend-Pakete (nur beim ersten Mal, dauert etwas)...' White
    Push-Location 'mtg-frontend'
    npm install
    Pop-Location
} else {
    Schreib '[3/3] Frontend-Pakete sind vorhanden.' White
}

# ---------------------------------------------------------------------------
# 3. Stripe vorbereiten
# ---------------------------------------------------------------------------
# Ohne die CLI laeuft alles andere trotzdem -- nur eben ohne Webhooks. Das ist
# ein Hinweis wert, aber kein Grund, den Start abzubrechen: an der Sammlung,
# den Decks und der KI kann man auch ohne Bezahlung arbeiten.
$StripeDa = Vorhanden 'stripe'
$LokalerWebhookSchluessel = $null

if ($StripeDa) {
    Schreib ''
    Schreib 'Frage den lokalen Webhook-Schluessel bei der Stripe-CLI ab...' White
    try {
        $LokalerWebhookSchluessel = (& stripe listen --print-secret 2>&1 | Out-String).Trim()
    } catch {
        $LokalerWebhookSchluessel = $null
    }

    if ($LokalerWebhookSchluessel -notmatch '^whsec_') {
        Schreib '[HINWEIS] Die Stripe-CLI konnte keinen Schluessel liefern.' Yellow
        Schreib '          Meistens fehlt die Anmeldung. Einmalig ausfuehren:' Yellow
        Schreib '              stripe login' Yellow
        Schreib '          Grana startet weiter, aber ohne Webhooks.' Yellow
        $LokalerWebhookSchluessel = $null
    } else {
        Schreib "Lokaler Schluessel: $($LokalerWebhookSchluessel.Substring(0,11))... (gilt nur fuer diesen Lauf)" Green
    }
} else {
    Schreib ''
    Schreib '[HINWEIS] Die Stripe-CLI wurde nicht gefunden.' Yellow
    Schreib '          Sammlung, Decks und KI funktionieren trotzdem.' Yellow
    Schreib '          NICHT funktionieren wird die Premium-Freischaltung nach' Yellow
    Schreib '          einem Testkauf: dafuer muss ein Webhook ankommen.' Yellow
    Schreib '          Installieren: https://docs.stripe.com/stripe-cli' Yellow
}

# ---------------------------------------------------------------------------
# 4. Starten
# ---------------------------------------------------------------------------
Titel 'Starte...'

try {
    # --- Backend ---
    # Der lokale Webhook-Schluessel wird nur diesem Prozess mitgegeben.
    # python-dotenv laesst eine gesetzte Umgebungsvariable stehen, die .env
    # bleibt also unangetastet und fuer den echten Betrieb richtig.
    if ($LokalerWebhookSchluessel) {
        $env:STRIPE_WEBHOOK_SECRET = $LokalerWebhookSchluessel
    }
    $Prozesse += StarteProgramm $VenvPython `
        @('-m', 'uvicorn', 'main:app', '--port', "$BackendPort", '--reload') `
        $PSScriptRoot
    Schreib "  Backend    http://localhost:$BackendPort" Green

    # --- Frontend ---
    $Prozesse += StarteProgramm 'npm' @('run', 'dev') `
        (Join-Path $PSScriptRoot 'mtg-frontend')
    Schreib "  Frontend   http://localhost:$FrontendPort" Green

    # --- Stripe ---
    # In einem eigenen try: Stripe ist die einzige der drei Komponenten, ohne
    # die man weiterarbeiten kann. Scheitert der Start hier, sollen Backend und
    # Frontend WEITERLAUFEN -- vorher riss ein Stripe-Fehler beides mit sich,
    # und man stand ohne alles da, obwohl nur die Bezahlung betroffen war.
    if ($LokalerWebhookSchluessel) {
        $Ziel = "localhost:$BackendPort$WebhookPfad"
        try {
            $Prozesse += StarteProgramm 'stripe' `
                @('listen', '--forward-to', $Ziel) $PSScriptRoot
            Schreib "  Stripe     leitet Webhooks an $Ziel" Green
        } catch {
            Schreib "  Stripe     LIESS SICH NICHT STARTEN: $($_.Exception.Message)" Yellow
            Schreib '             Backend und Frontend laufen weiter. Nicht gehen' Yellow
            Schreib '             wird die Premium-Freischaltung nach einem Testkauf.' Yellow
        }
    }

    Titel "Bereit -- oeffne http://localhost:$FrontendPort"
    Schreib 'Zum Beenden: Strg + C in DIESEM Fenster (stoppt alle Dienste).' DarkGray
    Schreib ''

    if ($LokalerWebhookSchluessel) {
        Schreib 'Testkauf mit dieser Kartennummer (Stripe-Testmodus):' DarkGray
        Schreib '    4242 4242 4242 4242, beliebiges Datum in der Zukunft, beliebige CVC' DarkGray
        Schreib ''
    }

    # Laufen lassen, bis der Nutzer abbricht -- oder bis ein Dienst von selbst
    # aussteigt. Ein Backend, das beim Start abstuerzt, soll nicht unbemerkt
    # fehlen, waehrend das Fenster weiter "Bereit" anzeigt.
    while ($true) {
        Start-Sleep -Seconds 1
        $Beendet = $Prozesse | Where-Object { $_.HasExited }
        if ($Beendet) {
            Schreib ''
            Schreib '[FEHLER] Ein Dienst hat sich beendet -- siehe die Meldungen oben.' Red
            Schreib '         Die anderen werden jetzt auch gestoppt.' Red
            break
        }
    }
}
finally {
    # Laeuft auch bei Strg + C. Ohne das bleiben Backend, Frontend und die
    # Stripe-CLI im Hintergrund liegen und blockieren beim naechsten Start
    # ihre Ports -- mit einer Fehlermeldung, die nichts damit zu tun zu haben
    # scheint.
    Write-Host ''
    Write-Host 'Beende alle Dienste...' -ForegroundColor DarkGray
    foreach ($p in $Prozesse) {
        if ($p -and -not $p.HasExited) {
            # Auch die Kindprozesse: "npm run dev" startet Vite als eigenen
            # Prozess, der sonst weiterlaeuft und Port 5175 belegt haelt.
            & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
        }
    }
    if ($env:STRIPE_WEBHOOK_SECRET) {
        Remove-Item Env:\STRIPE_WEBHOOK_SECRET -ErrorAction SilentlyContinue
    }
    Write-Host 'Fertig.' -ForegroundColor DarkGray
}
