# NekoTab Route Audit Script
# Tests all routes and reports status codes, redirects, and response times

$baseUrl = "https://nekotab.app"
$slug = "dc-2026"
$results = @()

function Test-Route {
    param(
        [string]$Url,
        [string]$Name,
        [string]$Expected,
        [string]$Category
    )
    
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-WebRequest -Uri $Url -Method GET -MaximumRedirection 0 -ErrorAction Stop -TimeoutSec 15 -UseBasicParsing
        $stopwatch.Stop()
        $status = $response.StatusCode
        $contentType = $response.Headers['Content-Type']
        $bodyLength = $response.Content.Length
        $redirect = ""
    }
    catch {
        $stopwatch.Stop()
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            $redirect = ""
            $contentType = ""
            $bodyLength = 0
            try {
                $redirect = $_.Exception.Response.Headers.Location
                if (-not $redirect) {
                    $redirect = $_.Exception.Response.Headers['Location']
                }
            } catch {}
            # For redirects, try to get Location header
            if ($status -ge 300 -and $status -lt 400) {
                try {
                    $redirect = $_.Exception.Response.Headers.Location.ToString()
                } catch {
                    $redirect = "unknown"
                }
            }
        }
        else {
            $status = "TIMEOUT/ERROR"
            $redirect = $_.Exception.Message
            $contentType = ""
            $bodyLength = 0
        }
    }
    
    $elapsed = $stopwatch.ElapsedMilliseconds
    
    $obj = [PSCustomObject]@{
        Category    = $Category
        URL         = $Url
        Name        = $Name
        Status      = $status
        Expected    = $Expected
        Redirect    = $redirect
        TimeMs      = $elapsed
        ContentType = $contentType
        BodyLength  = $bodyLength
    }
    
    # Color-code output
    $color = "Green"
    if ($status -eq 500) { $color = "Red" }
    elseif ($status -eq 404) { $color = "Yellow" }
    elseif ($status -eq 403) { $color = "Cyan" }
    elseif ($status -ge 300 -and $status -lt 400) { $color = "DarkYellow" }
    elseif ("$status" -match "TIMEOUT|ERROR") { $color = "Red" }
    
    Write-Host "$status | $elapsed ms | $Name | $Url" -ForegroundColor $color
    if ($redirect) { Write-Host "  -> $redirect" -ForegroundColor DarkGray }
    
    return $obj
}

Write-Host "========================================" -ForegroundColor White
Write-Host "NekoTab Route Audit - $(Get-Date)" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host ""

# ===========================================
# 1. ROOT SITE PAGES
# ===========================================
Write-Host "`n--- 1. ROOT SITE PAGES ---" -ForegroundColor Magenta

$rootRoutes = @(
    @("/", "Homepage", "200"),
    @("/start/", "Blank site start", "200"),
    @("/style/", "Style guide", "200"),
    @("/create/", "Create tournament", "200 or 302"),
    @("/create/ie/", "Create IE tournament", "200 or 302"),
    @("/create/congress/", "Create congress tournament", "200 or 302"),
    @("/register/tournament/", "Register + create tournament", "200"),
    @("/register/organization/", "Register + create org", "200"),
    @("/for-organizers/", "Marketing page", "200"),
    @("/free-debate-tab-software/", "SEO page", "200"),
    @("/bp-debate-tabulation/", "SEO page", "200"),
    @("/tabroom-alternative/", "SEO page", "200"),
    @("/sitemap.xml", "Sitemap", "200 XML"),
    @("/robots.txt", "Robots", "200 text"),
    @("/ads.txt", "Ads", "200 text"),
    @("/googlee0a2b1e83278e880.html", "Verification 1", "200"),
    @("/google4a7d5456478d704b.html", "Verification 2", "200"),
    @("/api/", "API root", "200 JSON"),
    @("/api/v1/", "API v1 root", "200 JSON"),
    @("/api/schema/", "OpenAPI schema", "200"),
    @("/api/schema/redoc/", "API docs", "200")
)

foreach ($r in $rootRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "Root"
}

# ===========================================
# 2. AUTH & ACCOUNTS
# ===========================================
Write-Host "`n--- 2. AUTH & ACCOUNTS ---" -ForegroundColor Magenta

$authRoutes = @(
    @("/accounts/login/", "Login", "200"),
    @("/accounts/signup/", "Signup", "200"),
    @("/accounts/password_reset/", "Password Reset", "200"),
    @("/accounts/password_reset/done/", "Password Reset Done", "200"),
    @("/accounts/logout/", "Logout", "302")
)

foreach ($r in $authRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "Auth"
}

# ===========================================
# 3. GLOBAL FEATURES
# ===========================================
Write-Host "`n--- 3. GLOBAL FEATURES ---" -ForegroundColor Magenta

$globalRoutes = @(
    @("/forum/", "Forum home", "200"),
    @("/motions-bank/", "Motion Bank home", "200"),
    @("/motions-bank/doctor/", "Motion Doctor", "200"),
    @("/passport/", "Passport directory", "200"),
    @("/organizations/", "Org list", "200 or 302"),
    @("/campaigns/", "Campaign list", "200 or 302"),
    @("/analytics/", "Analytics dashboard", "200 or 302/403"),
    @("/notifications/status/", "Email status", "200 or 302")
)

foreach ($r in $globalRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "Global"
}

# ===========================================
# 4A. PUBLIC TOURNAMENT PAGES (path-based)
# ===========================================
Write-Host "`n--- 4A. PUBLIC TOURNAMENT PAGES (path-based) ---" -ForegroundColor Magenta

$tourneyPublicRoutes = @(
    @("/", "Tournament homepage", "200"),
    @("/schedule/", "Public schedule", "200"),
    @("/draw/", "Current round draw", "200"),
    @("/draw/round/1/", "Draw for round 1", "200"),
    @("/draw/sides/", "Side allocations", "200"),
    @("/results/", "Public results index", "200"),
    @("/results/round/1/", "Results for round 1", "200"),
    @("/motions/", "Released motions", "200"),
    @("/motions/statistics/", "Motion statistics", "200"),
    @("/participants/list/", "Participant list", "200"),
    @("/participants/institutions/", "Institution list", "200"),
    @("/participants/team/1/", "Team record pk=1", "200 or 404"),
    @("/participants/adjudicator/1/", "Adj record pk=1", "200 or 404"),
    @("/standings/current-standings/", "Current team standings", "200"),
    @("/standings/team/", "Team tab", "200"),
    @("/standings/speaker/", "Speaker tab", "200"),
    @("/standings/replies/", "Reply tab", "200"),
    @("/standings/adjudicators/", "Adj tab", "200"),
    @("/standings/diversity/", "Diversity stats", "200"),
    @("/break/", "Break index", "200"),
    @("/break/adjudicators/", "Breaking adjs", "200"),
    @("/feedback/progress/", "Feedback progress", "200"),
    @("/checkins/status/people/", "Check-in status", "200"),
    @("/registration/", "Registration landing", "200")
)

foreach ($r in $tourneyPublicRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "TourneyPublic-Path"
}

# ===========================================
# 4A-sub. PUBLIC TOURNAMENT PAGES (subdomain-based)
# ===========================================
Write-Host "`n--- 4A-sub. PUBLIC TOURNAMENT PAGES (subdomain) ---" -ForegroundColor Magenta

foreach ($r in $tourneyPublicRoutes) {
    $results += Test-Route -Url "https://$slug.nekotab.app$($r[0])" -Name "$($r[1]) [subdomain]" -Expected $r[2] -Category "TourneyPublic-Subdomain"
}

# ===========================================
# 4B. CONGRESS PUBLIC PAGES
# ===========================================
Write-Host "`n--- 4B. CONGRESS PUBLIC PAGES ---" -ForegroundColor Magenta

$congressPublicRoutes = @(
    @("/congress/standings/", "Public standings", "200"),
    @("/congress/student/session/1/", "Student session view", "200 or 404")
)

foreach ($r in $congressPublicRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "CongressPublic"
}

# ===========================================
# 4C. IE PUBLIC PAGES
# ===========================================
Write-Host "`n--- 4C. IE PUBLIC PAGES ---" -ForegroundColor Magenta

$iePublicRoutes = @(
    @("/ie/", "Public IE dashboard", "200"),
    @("/ie/1/standings/", "IE event standings", "200 or 404")
)

foreach ($r in $iePublicRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "IEPublic"
}

# ===========================================
# 4D. ADMIN TOURNAMENT PAGES
# ===========================================
Write-Host "`n--- 4D. ADMIN TOURNAMENT PAGES ---" -ForegroundColor Magenta

$adminRoutes = @(
    @("/admin/", "Admin home", "200 or 302"),
    @("/admin/configure/", "Tournament config", "200 or 302"),
    @("/admin/options/", "Options index", "200 or 302"),
    @("/admin/participants/list/", "Admin participant list", "200 or 302"),
    @("/admin/participants/institutions/", "Admin institutions", "200 or 302"),
    @("/admin/participants/code-names/", "Code names", "200 or 302"),
    @("/admin/participants/eligibility/", "Speaker eligibility", "200 or 302"),
    @("/admin/participants/team/1/", "Admin team record", "200 or 302"),
    @("/admin/participants/adjudicator/1/", "Admin adj record", "200 or 302"),
    @("/admin/import/simple/", "Simple importer", "200 or 302"),
    @("/admin/import/export/", "Export page", "200 or 302"),
    @("/admin/privateurls/", "Private URLs list", "200 or 302"),
    @("/admin/availability/round/1/", "Availability for R1", "200 or 302"),
    @("/admin/availability/round/1/adjudicators/", "Adj availability", "200 or 302"),
    @("/admin/availability/round/1/teams/", "Team availability", "200 or 302"),
    @("/admin/availability/round/1/venues/", "Venue availability", "200 or 302"),
    @("/admin/draw/round/1/", "Admin draw for R1", "200 or 302"),
    @("/admin/draw/round/1/details/", "Draw details", "200 or 302"),
    @("/admin/draw/round/1/position-balance/", "Position balance", "200 or 302"),
    @("/admin/draw/round/1/display/", "Draw display", "200 or 302"),
    @("/admin/draw/round/current/display-by-venue/", "Current draw by venue", "200 or 302"),
    @("/admin/draw/round/current/display-by-team/", "Current draw by team", "200 or 302"),
    @("/admin/draw/sides/", "Side allocations", "200 or 302"),
    @("/admin/results/round/1/", "Admin results for R1", "200 or 302"),
    @("/admin/motions/round/1/edit/", "Edit motions R1", "200 or 302"),
    @("/admin/motions/round/1/display/", "Display motions R1", "200 or 302"),
    @("/admin/motions/statistics/", "Motion stats", "200 or 302"),
    @("/admin/feedback/", "Feedback overview", "200 or 302"),
    @("/admin/feedback/progress/", "Feedback progress", "200 or 302"),
    @("/admin/feedback/latest/", "Latest feedback", "200 or 302"),
    @("/admin/feedback/important/", "Important feedback", "200 or 302"),
    @("/admin/feedback/comments/", "Feedback comments", "200 or 302"),
    @("/admin/feedback/source/list/", "By source", "200 or 302"),
    @("/admin/feedback/target/list/", "By target", "200 or 302"),
    @("/admin/feedback/add/", "Add feedback index", "200 or 302"),
    @("/admin/standings/round/1/", "Admin standings R1", "200 or 302"),
    @("/admin/standings/round/1/team/", "Team standings R1", "200 or 302"),
    @("/admin/standings/round/1/speaker/", "Speaker standings R1", "200 or 302"),
    @("/admin/standings/round/1/reply/", "Reply standings R1", "200 or 302"),
    @("/admin/standings/round/1/diversity/", "Diversity R1", "200 or 302"),
    @("/admin/break/", "Break index", "200 or 302"),
    @("/admin/break/adjudicators/", "Breaking adjs", "200 or 302"),
    @("/admin/break/eligibility/", "Break eligibility", "200 or 302"),
    @("/admin/checkins/prescan/", "Check-in scanner", "200 or 302"),
    @("/admin/checkins/status/people/", "People check-in status", "200 or 302"),
    @("/admin/checkins/status/venues/", "Venue check-in status", "200 or 302"),
    @("/admin/checkins/identifiers/", "Check-in identifiers", "200 or 302"),
    @("/admin/allocations/conflicts/adjudicator-team/", "Adj-team conflicts", "200 or 302"),
    @("/admin/allocations/conflicts/adjudicator-adjudicator/", "Adj-adj conflicts", "200 or 302"),
    @("/admin/allocations/conflicts/adjudicator-institution/", "Adj-inst conflicts", "200 or 302"),
    @("/admin/allocations/conflicts/team-institution/", "Team-inst conflicts", "200 or 302"),
    @("/admin/allocations/panels/edit/", "Panel editor", "200 or 302"),
    @("/admin/printing/round/1/scoresheets/", "Print scoresheets", "200 or 302"),
    @("/admin/printing/round/1/feedback/", "Print feedback", "200 or 302"),
    @("/admin/printing/urls_sheets/teams/", "Print team URLs", "200 or 302"),
    @("/admin/printing/urls_sheets/adjudicators/", "Print adj URLs", "200 or 302"),
    @("/admin/users/", "Admin user management", "200 or 302"),
    @("/admin/notifications/", "Admin notifications", "200 or 302"),
    @("/admin/registration/institutions/", "Reg institutions", "200 or 302"),
    @("/admin/registration/teams/", "Reg teams", "200 or 302"),
    @("/admin/registration/adjudicators/", "Reg adjudicators", "200 or 302")
)

foreach ($r in $adminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "Admin"
}

# ===========================================
# 4E. CONGRESS ADMIN PAGES
# ===========================================
Write-Host "`n--- 4E. CONGRESS ADMIN PAGES ---" -ForegroundColor Magenta

$congressAdminRoutes = @(
    @("/admin/congress/", "Congress dashboard", "200 or 302"),
    @("/admin/congress/setup/", "Congress setup wizard", "200 or 302"),
    @("/admin/congress/docket/", "Docket manager", "200 or 302"),
    @("/admin/congress/chambers/", "Chamber manager", "200 or 302"),
    @("/admin/congress/session/1/", "Session view", "200 or 302"),
    @("/admin/congress/session/1/scorer/", "Scorer view", "200 or 302"),
    @("/admin/congress/standings/", "Admin standings", "200 or 302"),
    @("/admin/congress/session/1/po/", "PO view", "200 or 302")
)

foreach ($r in $congressAdminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "CongressAdmin"
}

# ===========================================
# 4F. IE ADMIN PAGES
# ===========================================
Write-Host "`n--- 4F. IE ADMIN PAGES ---" -ForegroundColor Magenta

$ieAdminRoutes = @(
    @("/admin/ie/", "IE dashboard", "200 or 302"),
    @("/admin/ie/setup/", "IE setup wizard", "200 or 302"),
    @("/admin/ie/prep/", "Tournament prep", "200 or 302"),
    @("/admin/ie/prep/all/", "All prep data", "200 or 302"),
    @("/admin/ie/prep/institutions/", "Prep institutions", "200 or 302"),
    @("/admin/ie/prep/speakers/", "Prep speakers", "200 or 302"),
    @("/admin/ie/prep/judges/", "Prep judges", "200 or 302"),
    @("/admin/ie/1/entries/", "Entry manager", "200 or 302"),
    @("/admin/ie/1/draw/1/", "Room draw", "200 or 302"),
    @("/admin/ie/1/standings/", "IE standings", "200 or 302"),
    @("/admin/ie/1/finalists/", "Finalists", "200 or 302"),
    @("/admin/ie/1/judge-links/1/page/", "Judge links page", "200 or 302")
)

foreach ($r in $ieAdminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "IEAdmin"
}

# ===========================================
# 4G. ASSISTANT PAGES
# ===========================================
Write-Host "`n--- 4G. ASSISTANT PAGES ---" -ForegroundColor Magenta

$assistantRoutes = @(
    @("/assistant/", "Assistant home", "200 or 302"),
    @("/assistant/draw/display/", "Draw display", "200 or 302"),
    @("/assistant/results/", "Results list", "200 or 302"),
    @("/assistant/feedback/add/", "Add feedback", "200 or 302"),
    @("/assistant/checkins/prescan/", "Check-in scan", "200 or 302"),
    @("/assistant/checkins/status/people/", "Check-in status", "200 or 302"),
    @("/assistant/checkins/status/venues/", "Venue status", "200 or 302"),
    @("/assistant/participants/list/", "Participant list", "200 or 302"),
    @("/assistant/participants/institutions/", "Institutions", "200 or 302"),
    @("/assistant/motions/display/", "Motions display", "200 or 302"),
    @("/assistant/printing/scoresheets/", "Print scoresheets", "200 or 302"),
    @("/assistant/printing/feedback/", "Print feedback", "200 or 302")
)

foreach ($r in $assistantRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "Assistant"
}

# ===========================================
# 5. REST API ENDPOINTS
# ===========================================
Write-Host "`n--- 5. REST API ENDPOINTS ---" -ForegroundColor Magenta

$apiRoutes = @(
    @("/api/v1/institutions", "Institutions list", "200 JSON"),
    @("/api/v1/users", "Users list", "200 or 401"),
    @("/api/v1/users/me", "Current user", "200 or 401"),
    @("/api/v1/tournaments/$slug/", "Tournament detail", "200 JSON"),
    @("/api/v1/tournaments/$slug/teams", "Teams", "200 JSON"),
    @("/api/v1/tournaments/$slug/adjudicators", "Adjudicators", "200 JSON"),
    @("/api/v1/tournaments/$slug/speakers", "Speakers", "200 JSON"),
    @("/api/v1/tournaments/$slug/venues", "Venues", "200 JSON"),
    @("/api/v1/tournaments/$slug/motions", "Motions", "200 JSON"),
    @("/api/v1/tournaments/$slug/rounds", "Rounds", "200 JSON"),
    @("/api/v1/tournaments/$slug/rounds/1/pairings", "Pairings R1", "200 JSON"),
    @("/api/v1/tournaments/$slug/rounds/1/availabilities", "Availabilities R1", "200 JSON"),
    @("/api/v1/tournaments/$slug/feedback", "Feedback", "200 JSON"),
    @("/api/v1/tournaments/$slug/feedback-questions", "Feedback questions", "200 JSON"),
    @("/api/v1/tournaments/$slug/break-categories", "Break categories", "200 JSON"),
    @("/api/v1/tournaments/$slug/speaker-categories", "Speaker categories", "200 JSON"),
    @("/api/v1/tournaments/$slug/venue-categories", "Venue categories", "200 JSON"),
    @("/api/v1/tournaments/$slug/teams/standings", "Teams standings", "200 JSON"),
    @("/api/v1/tournaments/$slug/speakers/standings", "Speakers standings", "200 JSON"),
    @("/api/v1/tournaments/$slug/institutions", "Tournament institutions", "200 JSON"),
    @("/api/v1/tournaments/$slug/me", "Tournament me", "200 or 401")
)

foreach ($r in $apiRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "API"
}

# ===========================================
# 6. MICROSERVICE PROXIED ENDPOINTS
# ===========================================
Write-Host "`n--- 6. MICROSERVICE PROXIED ENDPOINTS ---" -ForegroundColor Magenta

$microRoutes = @(
    @("/api/ie/docs", "nekospeech docs", "200 HTML"),
    @("/api/ie/health", "nekospeech health", "200 JSON"),
    @("/api/congress/docs", "nekocongress docs", "200 HTML"),
    @("/api/congress/health", "nekocongress health", "200 JSON")
)

foreach ($r in $microRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "Microservice"
}

# ===========================================
# EDGE CASE TESTS - SUBDOMAIN ROUTING
# ===========================================
Write-Host "`n--- EDGE CASES: SUBDOMAIN ROUTING ---" -ForegroundColor Magenta

$subdomainTests = @(
    @("https://dc-2026.nekotab.app/", "Valid subdomain", "200"),
    @("https://nonexistent.nekotab.app/", "Invalid subdomain", "404"),
    @("https://admin.nekotab.app/", "Reserved: admin", "redirect or 404"),
    @("https://www.nekotab.app/", "Reserved: www", "redirect or 200"),
    @("https://api.nekotab.app/", "Reserved: api", "redirect or 404"),
    @("https://dc-2026.nekotab.app/dc-2026/admin/", "Double slug", "should not double-prefix")
)

foreach ($r in $subdomainTests) {
    $results += Test-Route -Url $r[0] -Name $r[1] -Expected $r[2] -Category "SubdomainEdge"
}

# ===========================================
# EDGE CASE TESTS - PATH EDGE CASES
# ===========================================
Write-Host "`n--- EDGE CASES: PATH ---" -ForegroundColor Magenta

$pathEdgeCases = @(
    @("$baseUrl/$slug/admin/congress", "Trailing slash missing", "301 or 200"),
    @("$baseUrl/$slug/admin/congress/", "Trailing slash present", "200 or 302"),
    @("$baseUrl/$slug/admin/draw/round/999/", "Nonexistent round", "404 not 500"),
    @("$baseUrl/$slug/participants/team/999999/", "Nonexistent team PK", "404 not 500"),
    @("$baseUrl/$slug/participants/adjudicator/999999/", "Nonexistent adj PK", "404 not 500"),
    @("$baseUrl/$slug/admin/draw/round/0/", "Zero round", "404 not 500"),
    @("$baseUrl/$slug/admin/draw/round/-1/", "Negative round", "404 not 500"),
    @("$baseUrl/$slug/admin/congress/session/abc/", "String where int expected", "404 not 500")
)

foreach ($r in $pathEdgeCases) {
    $results += Test-Route -Url $r[0] -Name $r[1] -Expected $r[2] -Category "PathEdge"
}

# ===========================================
# SUMMARY REPORT
# ===========================================
Write-Host "`n`n========================================" -ForegroundColor White
Write-Host "AUDIT SUMMARY REPORT" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White

$critical = $results | Where-Object { $_.Status -eq 500 }
$broken = $results | Where-Object { $_.Status -eq 404 -and $_.Expected -notmatch "404" }
$unexpectedForbidden = $results | Where-Object { $_.Status -eq 403 -and $_.Expected -notmatch "403" }
$slow = $results | Where-Object { $_.TimeMs -gt 5000 }
$errors = $results | Where-Object { "$($_.Status)" -match "TIMEOUT|ERROR" }
$redirects = $results | Where-Object { $_.Status -ge 300 -and $_.Status -lt 400 }

Write-Host "`n### Critical Errors (500) ###" -ForegroundColor Red
if ($critical.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else { $critical | Format-Table URL, Name, TimeMs -AutoSize }

Write-Host "`n### Unexpected Broken Links (404 where not expected) ###" -ForegroundColor Yellow
if ($broken.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else { $broken | Format-Table URL, Name, Expected -AutoSize }

Write-Host "`n### Unexpected 403 Forbidden ###" -ForegroundColor Cyan
if ($unexpectedForbidden.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else { $unexpectedForbidden | Format-Table URL, Name, Expected -AutoSize }

Write-Host "`n### Performance Issues (>5s) ###" -ForegroundColor Yellow
if ($slow.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else { $slow | Format-Table URL, Name, TimeMs -AutoSize }

Write-Host "`n### Timeouts/Connection Errors ###" -ForegroundColor Red
if ($errors.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else { $errors | Format-Table URL, Name, Status, Redirect -AutoSize }

Write-Host "`n### Redirects ###" -ForegroundColor DarkYellow
$redirects | Format-Table Status, URL, Name, Redirect -AutoSize

Write-Host "`n### Full Results ###" -ForegroundColor White
Write-Host "Total routes tested: $($results.Count)"
$results | Group-Object Status | Sort-Object Name | Format-Table Name, Count -AutoSize

# Export to CSV
$csvPath = "d:\Sumon\Coding\nekotab-app\route_audit_results.csv"
$results | Export-Csv -Path $csvPath -NoTypeInformation
Write-Host "`nResults exported to: $csvPath" -ForegroundColor Green
