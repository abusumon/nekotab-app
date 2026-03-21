# NekoTab Route Audit Script v2 - Using .NET HttpWebRequest for accurate status codes
# Fixes the "Operation is not valid" issue from Invoke-WebRequest

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
    $status = ""
    $redirect = ""
    $contentType = ""
    $bodyLength = 0
    
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = "GET"
        $request.AllowAutoRedirect = $false
        $request.Timeout = 15000
        $request.UserAgent = "NekoTab-RouteAudit/1.0"
        
        $response = $request.GetResponse()
        $stopwatch.Stop()
        $status = [int]$response.StatusCode
        $contentType = $response.ContentType
        $bodyLength = $response.ContentLength
        $redirect = $response.Headers["Location"]
        $response.Close()
    }
    catch [System.Net.WebException] {
        $stopwatch.Stop()
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            $contentType = $_.Exception.Response.ContentType
            $redirect = $_.Exception.Response.Headers["Location"]
            $_.Exception.Response.Close()
        }
        else {
            $status = "ERROR"
            $redirect = $_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length))
        }
    }
    catch {
        $stopwatch.Stop()
        $status = "ERROR"
        $redirect = $_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length))
    }
    
    $elapsed = $stopwatch.ElapsedMilliseconds
    
    # Color-code output
    $color = "Green"
    if ($status -eq 500) { $color = "Red" }
    elseif ($status -eq 404) { $color = "Yellow" }
    elseif ($status -eq 403) { $color = "Cyan" }
    elseif ($status -ge 300 -and $status -lt 400) { $color = "DarkYellow" }
    elseif ($status -eq 401) { $color = "DarkCyan" }
    elseif ("$status" -eq "ERROR") { $color = "Red" }
    
    $display = "{0,4} | {1,5}ms | {2,-40} | {3}" -f $status, $elapsed, $Name, $Url
    Write-Host $display -ForegroundColor $color
    if ($redirect) { Write-Host ("  -> {0}" -f $redirect) -ForegroundColor DarkGray }
    
    $obj = [PSCustomObject]@{
        Category    = $Category
        URL         = $Url
        Name        = $Name
        Status      = $status
        Expected    = $Expected
        Redirect    = $redirect
        TimeMs      = $elapsed
        ContentType = $contentType
    }
    
    return $obj
}

Write-Host "========================================" -ForegroundColor White
Write-Host "NekoTab Route Audit v2 - $(Get-Date)" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor White

# ===========================================
# 1. ROOT SITE PAGES
# ===========================================
Write-Host "--- 1. ROOT SITE PAGES ---" -ForegroundColor Magenta

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
    @("/bp-debate-tabulation/", "SEO page BP", "200"),
    @("/tabroom-alternative/", "SEO page Tabroom", "200"),
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
# 4A-sub. PUBLIC TOURNAMENT PAGES (subdomain)
# ===========================================
Write-Host "`n--- 4A-sub. PUBLIC TOURNAMENT PAGES (subdomain) ---" -ForegroundColor Magenta

foreach ($r in $tourneyPublicRoutes) {
    $results += Test-Route -Url "https://$slug.nekotab.app$($r[0])" -Name "$($r[1]) [sub]" -Expected $r[2] -Category "TourneyPublic-Sub"
}

# ===========================================
# 4B. CONGRESS PUBLIC PAGES
# ===========================================
Write-Host "`n--- 4B. CONGRESS PUBLIC PAGES ---" -ForegroundColor Magenta

$congressPublicRoutes = @(
    @("/congress/standings/", "Congress pub standings", "200"),
    @("/congress/student/session/1/", "Student session view", "200 or 404")
)

foreach ($r in $congressPublicRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected $r[2] -Category "CongressPublic"
    $results += Test-Route -Url "https://$slug.nekotab.app$($r[0])" -Name "$($r[1]) [sub]" -Expected $r[2] -Category "CongressPublic-Sub"
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
    $results += Test-Route -Url "https://$slug.nekotab.app$($r[0])" -Name "$($r[1]) [sub]" -Expected $r[2] -Category "IEPublic-Sub"
}

# ===========================================
# 4D. ADMIN PAGES (path-based only, login-required → expect 302)
# ===========================================
Write-Host "`n--- 4D. ADMIN TOURNAMENT PAGES ---" -ForegroundColor Magenta

$adminRoutes = @(
    @("/admin/", "Admin home"),
    @("/admin/configure/", "Tournament config"),
    @("/admin/options/", "Options index"),
    @("/admin/participants/list/", "Admin participant list"),
    @("/admin/participants/institutions/", "Admin institutions"),
    @("/admin/participants/code-names/", "Code names"),
    @("/admin/participants/eligibility/", "Speaker eligibility"),
    @("/admin/participants/team/1/", "Admin team record"),
    @("/admin/participants/adjudicator/1/", "Admin adj record"),
    @("/admin/import/simple/", "Simple importer"),
    @("/admin/import/export/", "Export page"),
    @("/admin/privateurls/", "Private URLs list"),
    @("/admin/availability/round/1/", "Availability for R1"),
    @("/admin/availability/round/1/adjudicators/", "Adj availability"),
    @("/admin/availability/round/1/teams/", "Team availability"),
    @("/admin/availability/round/1/venues/", "Venue availability"),
    @("/admin/draw/round/1/", "Admin draw for R1"),
    @("/admin/draw/round/1/details/", "Draw details"),
    @("/admin/draw/round/1/position-balance/", "Position balance"),
    @("/admin/draw/round/1/display/", "Draw display"),
    @("/admin/draw/round/current/display-by-venue/", "Current draw by venue"),
    @("/admin/draw/round/current/display-by-team/", "Current draw by team"),
    @("/admin/draw/sides/", "Side allocations"),
    @("/admin/results/round/1/", "Admin results for R1"),
    @("/admin/motions/round/1/edit/", "Edit motions R1"),
    @("/admin/motions/round/1/display/", "Display motions R1"),
    @("/admin/motions/statistics/", "Motion stats"),
    @("/admin/feedback/", "Feedback overview"),
    @("/admin/feedback/progress/", "Feedback progress"),
    @("/admin/feedback/latest/", "Latest feedback"),
    @("/admin/feedback/important/", "Important feedback"),
    @("/admin/feedback/comments/", "Feedback comments"),
    @("/admin/feedback/source/list/", "By source"),
    @("/admin/feedback/target/list/", "By target"),
    @("/admin/feedback/add/", "Add feedback index"),
    @("/admin/standings/round/1/", "Admin standings R1"),
    @("/admin/standings/round/1/team/", "Team standings R1"),
    @("/admin/standings/round/1/speaker/", "Speaker standings R1"),
    @("/admin/standings/round/1/reply/", "Reply standings R1"),
    @("/admin/standings/round/1/diversity/", "Diversity R1"),
    @("/admin/break/", "Break index"),
    @("/admin/break/adjudicators/", "Breaking adjs"),
    @("/admin/break/eligibility/", "Break eligibility"),
    @("/admin/checkins/prescan/", "Check-in scanner"),
    @("/admin/checkins/status/people/", "People check-in status"),
    @("/admin/checkins/status/venues/", "Venue check-in status"),
    @("/admin/checkins/identifiers/", "Check-in identifiers"),
    @("/admin/allocations/conflicts/adjudicator-team/", "Adj-team conflicts"),
    @("/admin/allocations/conflicts/adjudicator-adjudicator/", "Adj-adj conflicts"),
    @("/admin/allocations/conflicts/adjudicator-institution/", "Adj-inst conflicts"),
    @("/admin/allocations/conflicts/team-institution/", "Team-inst conflicts"),
    @("/admin/allocations/panels/edit/", "Panel editor"),
    @("/admin/printing/round/1/scoresheets/", "Print scoresheets"),
    @("/admin/printing/round/1/feedback/", "Print feedback"),
    @("/admin/printing/urls_sheets/teams/", "Print team URLs"),
    @("/admin/printing/urls_sheets/adjudicators/", "Print adj URLs"),
    @("/admin/users/", "Admin user management"),
    @("/admin/notifications/", "Admin notifications"),
    @("/admin/registration/institutions/", "Reg institutions"),
    @("/admin/registration/teams/", "Reg teams"),
    @("/admin/registration/adjudicators/", "Reg adjudicators")
)

foreach ($r in $adminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected "200 or 302" -Category "Admin-Path"
}

# Also test admin via subdomain
Write-Host "`n--- 4D-sub. ADMIN (subdomain, selected) ---" -ForegroundColor Magenta

$adminSubdomainSample = @(
    @("/admin/", "Admin home [sub]"),
    @("/admin/configure/", "Tournament config [sub]"),
    @("/admin/draw/round/1/", "Admin draw R1 [sub]"),
    @("/admin/results/round/1/", "Admin results R1 [sub]"),
    @("/admin/feedback/", "Feedback overview [sub]"),
    @("/admin/feedback/important/", "Important feedback [sub]"),
    @("/admin/printing/urls_sheets/teams/", "Print team URLs [sub]"),
    @("/admin/users/", "Admin users [sub]"),
    @("/admin/congress/", "Congress dashboard [sub]"),
    @("/admin/ie/", "IE dashboard [sub]")
)

foreach ($r in $adminSubdomainSample) {
    $results += Test-Route -Url "https://$slug.nekotab.app$($r[0])" -Name $r[1] -Expected "200 or 302" -Category "Admin-Sub"
}

# ===========================================
# 4E. CONGRESS ADMIN PAGES
# ===========================================
Write-Host "`n--- 4E. CONGRESS ADMIN PAGES ---" -ForegroundColor Magenta

$congressAdminRoutes = @(
    @("/admin/congress/", "Congress dashboard"),
    @("/admin/congress/setup/", "Congress setup wizard"),
    @("/admin/congress/docket/", "Docket manager"),
    @("/admin/congress/chambers/", "Chamber manager"),
    @("/admin/congress/session/1/", "Session view"),
    @("/admin/congress/session/1/scorer/", "Scorer view"),
    @("/admin/congress/standings/", "Admin standings"),
    @("/admin/congress/session/1/po/", "PO view")
)

foreach ($r in $congressAdminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected "200 or 302" -Category "CongressAdmin"
}

# ===========================================
# 4F. IE ADMIN PAGES
# ===========================================
Write-Host "`n--- 4F. IE ADMIN PAGES ---" -ForegroundColor Magenta

$ieAdminRoutes = @(
    @("/admin/ie/", "IE dashboard"),
    @("/admin/ie/setup/", "IE setup wizard"),
    @("/admin/ie/prep/", "Tournament prep"),
    @("/admin/ie/prep/all/", "All prep data"),
    @("/admin/ie/prep/institutions/", "Prep institutions"),
    @("/admin/ie/prep/speakers/", "Prep speakers"),
    @("/admin/ie/prep/judges/", "Prep judges"),
    @("/admin/ie/1/entries/", "Entry manager"),
    @("/admin/ie/1/draw/1/", "Room draw"),
    @("/admin/ie/1/standings/", "IE standings"),
    @("/admin/ie/1/finalists/", "Finalists"),
    @("/admin/ie/1/judge-links/1/page/", "Judge links page")
)

foreach ($r in $ieAdminRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected "200 or 302" -Category "IEAdmin"
}

# ===========================================
# 4G. ASSISTANT PAGES
# ===========================================
Write-Host "`n--- 4G. ASSISTANT PAGES ---" -ForegroundColor Magenta

$assistantRoutes = @(
    @("/assistant/", "Assistant home"),
    @("/assistant/draw/display/", "Draw display"),
    @("/assistant/results/", "Results list"),
    @("/assistant/feedback/add/", "Add feedback"),
    @("/assistant/checkins/prescan/", "Check-in scan"),
    @("/assistant/checkins/status/people/", "Check-in status"),
    @("/assistant/checkins/status/venues/", "Venue status"),
    @("/assistant/participants/list/", "Participant list"),
    @("/assistant/participants/institutions/", "Institutions"),
    @("/assistant/motions/display/", "Motions display"),
    @("/assistant/printing/scoresheets/", "Print scoresheets"),
    @("/assistant/printing/feedback/", "Print feedback")
)

foreach ($r in $assistantRoutes) {
    $results += Test-Route -Url "$baseUrl/$slug$($r[0])" -Name $r[1] -Expected "200 or 302" -Category "Assistant"
}

# ===========================================
# 5. REST API
# ===========================================
Write-Host "`n--- 5. REST API ENDPOINTS ---" -ForegroundColor Magenta

$apiRoutes = @(
    @("/api/v1/institutions", "Institutions list", "200 or 401"),
    @("/api/v1/users", "Users list", "200 or 401"),
    @("/api/v1/users/me", "Current user", "200 or 401"),
    @("/api/v1/tournaments/$slug/", "Tournament detail", "200"),
    @("/api/v1/tournaments/$slug/teams", "Teams", "200 or 401"),
    @("/api/v1/tournaments/$slug/adjudicators", "Adjudicators", "200 or 401"),
    @("/api/v1/tournaments/$slug/speakers", "Speakers", "200 or 401"),
    @("/api/v1/tournaments/$slug/venues", "Venues", "200"),
    @("/api/v1/tournaments/$slug/motions", "Motions", "200 or 401"),
    @("/api/v1/tournaments/$slug/rounds", "Rounds", "200"),
    @("/api/v1/tournaments/$slug/rounds/1/pairings", "Pairings R1", "200 or 401"),
    @("/api/v1/tournaments/$slug/rounds/1/availabilities", "Availabilities R1", "200 or 401"),
    @("/api/v1/tournaments/$slug/feedback", "Feedback", "200 or 401"),
    @("/api/v1/tournaments/$slug/feedback-questions", "Feedback questions", "200"),
    @("/api/v1/tournaments/$slug/break-categories", "Break categories", "200"),
    @("/api/v1/tournaments/$slug/speaker-categories", "Speaker categories", "200"),
    @("/api/v1/tournaments/$slug/venue-categories", "Venue categories", "200"),
    @("/api/v1/tournaments/$slug/teams/standings", "Teams standings", "200 or 401"),
    @("/api/v1/tournaments/$slug/speakers/standings", "Speakers standings", "200 or 401"),
    @("/api/v1/tournaments/$slug/institutions", "Tournament institutions", "200 or 401"),
    @("/api/v1/tournaments/$slug/me", "Tournament me", "200 or 401")
)

foreach ($r in $apiRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "API"
}

# ===========================================
# 6. MICROSERVICE
# ===========================================
Write-Host "`n--- 6. MICROSERVICE PROXIED ---" -ForegroundColor Magenta

$microRoutes = @(
    @("/api/ie/docs", "nekospeech docs", "200"),
    @("/api/ie/health", "nekospeech health", "200"),
    @("/api/congress/docs", "nekocongress docs", "200"),
    @("/api/congress/health", "nekocongress health", "200")
)

foreach ($r in $microRoutes) {
    $results += Test-Route -Url "$baseUrl$($r[0])" -Name $r[1] -Expected $r[2] -Category "Microservice"
}

# ===========================================
# EDGE CASES: SUBDOMAIN ROUTING
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
# EDGE CASES: PATH
# ===========================================
Write-Host "`n--- EDGE CASES: PATH ---" -ForegroundColor Magenta

$pathEdgeCases = @(
    @("$baseUrl/$slug/admin/congress", "No trailing slash", "301 or 200"),
    @("$baseUrl/$slug/admin/congress/", "With trailing slash", "200 or 302"),
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
$unexpected403 = $results | Where-Object { $_.Status -eq 403 -and $_.Expected -notmatch "403" }
$slow = $results | Where-Object { $_.TimeMs -gt 5000 }
$errors = $results | Where-Object { "$($_.Status)" -eq "ERROR" }
$redirects = $results | Where-Object { $_.Status -ge 300 -and $_.Status -lt 400 }

Write-Host "`n### CRITICAL ERRORS (500) - P0 ###" -ForegroundColor Red
if ($critical.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else {
    foreach ($c in $critical) {
        Write-Host ("  500 | {0} | {1}" -f $c.Name, $c.URL) -ForegroundColor Red
    }
}

Write-Host "`n### UNEXPECTED 404s ###" -ForegroundColor Yellow
if ($broken.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else {
    foreach ($b in $broken) {
        Write-Host ("  404 | {0,-40} | {1}" -f $b.Name, $b.URL) -ForegroundColor Yellow
    }
}

Write-Host "`n### UNEXPECTED 403 (Forbidden on public routes) ###" -ForegroundColor Cyan
if ($unexpected403.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else {
    foreach ($u in $unexpected403) {
        Write-Host ("  403 | {0,-40} | {1}" -f $u.Name, $u.URL) -ForegroundColor Cyan
    }
}

Write-Host "`n### PERFORMANCE ISSUES (>5s) ###" -ForegroundColor Yellow
if ($slow.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else {
    foreach ($s in $slow) {
        Write-Host ("  {0}ms | {1,-40} | {2}" -f $s.TimeMs, $s.Name, $s.URL) -ForegroundColor Yellow
    }
}

Write-Host "`n### CONNECTION ERRORS ###" -ForegroundColor Red
if ($errors.Count -eq 0) { Write-Host "  None found" -ForegroundColor Green }
else {
    foreach ($e in $errors) {
        Write-Host ("  ERROR | {0,-40} | {1} | {2}" -f $e.Name, $e.URL, $e.Redirect) -ForegroundColor Red
    }
}

Write-Host "`n### ALL REDIRECTS (302/301) ###" -ForegroundColor DarkYellow
foreach ($rd in $redirects) {
    Write-Host ("  {0} | {1,-40} | -> {2}" -f $rd.Status, $rd.Name, $rd.Redirect) -ForegroundColor DarkYellow
}

Write-Host "`n### STATUS CODE SUMMARY ###" -ForegroundColor White
Write-Host ("Total routes tested: {0}" -f $results.Count) -ForegroundColor White
$results | Group-Object Status | Sort-Object Name | Format-Table @{N="Status";E={$_.Name}}, Count -AutoSize

# Export to CSV
$csvPath = "d:\Sumon\Coding\nekotab-app\route_audit_results_v2.csv"
$results | Export-Csv -Path $csvPath -NoTypeInformation
Write-Host "Results exported to: $csvPath" -ForegroundColor Green
