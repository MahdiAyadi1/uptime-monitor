# M4 Manual Azure Deployment Runbook

This runbook deploys the current uptime-monitor API and scheduled checker to Azure Container Apps, using Azure Container Registry, Azure Database for PostgreSQL Flexible Server, Key Vault, and Log Analytics. The commands are for you to run from PowerShell; the agent does not sign in to Azure or create cloud resources.

The selected region is `westeurope`. The runbook intentionally deploys only the API, database, and checker for M4. Grafana is a later milestone. Per the project decision, TLS-expiry probing and webhook notifications are not part of this deployment.

## Before You Start

- Confirm your Azure budget alert is active and check current prices for West Europe in the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/). PostgreSQL Flexible Server is the largest likely fixed cost. This runbook does not estimate or guarantee prices.
- Use a new, dedicated resource group for this demo. The cleanup command at the end deletes everything in that group.
- Install Azure CLI and sign in with an account allowed to create resources and role assignments. The commands below target Windows PowerShell.
- Open a PowerShell terminal at the repository root. A local PostgreSQL server or Docker daemon is not required for the deployment or migration; the existing project virtual environment provides Python, Alembic, SQLAlchemy, and psycopg.
- Have the project files you intend to deploy committed or otherwise reviewed. `az acr build` builds the current working directory and sends its build context to Azure Container Registry.

## 1. Prepare Azure CLI

```powershell
az --version
```

This displays the installed CLI version and confirms that `az` is on your `PATH`. If the command is missing, install Azure CLI using Microsoft's [Windows instructions](https://learn.microsoft.com/cli/azure/install-azure-cli-windows).

```powershell
az upgrade
```

This updates the Azure CLI used by the remaining commands. Review the upgrade output and reopen PowerShell if the installer asks you to.

```powershell
az extension add --name containerapp --upgrade
```

This installs or updates the Container Apps CLI extension, which provides the `az containerapp` and scheduled-job commands used below.

```powershell
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.DBforPostgreSQL
az provider register --namespace Microsoft.ManagedIdentity
az provider register --namespace Microsoft.KeyVault
```

These register the Azure resource providers needed for Container Apps, logs, the registry, PostgreSQL, managed identity, and Key Vault in your subscription. Registration is a subscription setup operation, not creation of billable project resources. You can check a provider's state with `az provider show --namespace Microsoft.App --query registrationState --output tsv`; it should report `Registered`.

## 2. Sign In and Select the Subscription

```powershell
az login
```

This opens the Azure sign-in flow in your browser. Sign in with the account that owns the budget alert and has permission to create the demo resources.

```powershell
az account list --query "[].{Name:name, Id:id, State:state}" --output table
```

This lists subscriptions available to your account. Identify the subscription intended for the demo; do not assume the first listed subscription is correct.

```powershell
$SubscriptionId = Read-Host "Paste the demo subscription ID"
az account set --subscription $SubscriptionId
az account show --query "{Name:name, Id:id, State:state}" --output table
```

The first line stores the subscription ID in a PowerShell variable. `az account set` makes that subscription the target for subsequent Azure commands. The final command displays the active selection; verify it before creating anything.

## 3. Set Deployment Names and Generate Secrets

```powershell
$Location = "westeurope"
$Suffix = (Get-Random -Minimum 100000 -Maximum 999999).ToString()
$ResourceGroup = "rg-uptime-monitor-demo-$Suffix"
$RegistryName = "uptimemonitor$Suffix"
$KeyVaultName = "uptimekv$Suffix"
$PostgresServerName = "uptime-pg-$Suffix"
$WorkspaceName = "uptime-logs-$Suffix"
$EnvironmentName = "uptime-env-$Suffix"
$IdentityName = "uptime-runtime-$Suffix"
$ApiAppName = "uptime-api-$Suffix"
$CheckerJobName = "uptime-checker-$Suffix"
$DatabaseName = "uptime_monitor"
$PostgresAdminUser = "uptimeadmin"
$ApplicationDbUser = "uptime_monitor"
$ImageTag = (git rev-parse --short HEAD).Trim()
$ExpiresOn = Read-Host "Enter the planned Azure teardown date as YYYY-MM-DD"
```

These assignments keep names consistent for later commands. The random suffix makes the globally unique ACR, Key Vault, and PostgreSQL names less likely to collide. Resource names are deliberately generic and contain no personal information. The Git commit hash tags the image; check `git status --short` and confirm the source is the version you intend to deploy. Enter a real expiry date so resources can be identified for teardown.

```powershell
function New-UrlSafeSecret {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        return "Aa9-" + [Convert]::ToBase64String($bytes).TrimEnd([char]"=").Replace("+", "-").Replace("/", "_")
    }
    finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

$PostgresAdminPassword = New-UrlSafeSecret
$ApplicationDbPassword = New-UrlSafeSecret
$ApiKey = New-UrlSafeSecret
```

The function creates high-entropy URL-safe values for the PostgreSQL administrator, the least-privilege application role, and the API key. The `Aa9-` prefix ensures the PostgreSQL password includes multiple character classes. These values are assigned only to variables and are not printed. Do not paste them into chat, source files, or Git. They will be stored in Key Vault where the running application needs them.

## 4. Create the Resource Group and Logging Environment

Before continuing, reconfirm that the active subscription is correct and the budget alert is active. Container Apps and PostgreSQL can incur charges while provisioned, even when you are not testing the API.

```powershell
az group create --name $ResourceGroup --location $Location --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
```

This creates the dedicated resource group that will contain all M4 resources. The tags make the project and planned expiry searchable in the Azure portal and cost views. Verify the returned `location` and `name` before moving on.

```powershell
az monitor log-analytics workspace create --resource-group $ResourceGroup --workspace-name $WorkspaceName --location $Location --retention-time 30 --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
```

This creates the Log Analytics workspace that will collect Container Apps stdout/stderr logs. Thirty days is a short demo retention period. Log ingestion is usage-based, so inspect workspace usage and costs during the demo.

```powershell
$WorkspaceId = az monitor log-analytics workspace show --resource-group $ResourceGroup --workspace-name $WorkspaceName --query customerId --output tsv
$WorkspaceKey = az monitor log-analytics workspace get-shared-keys --resource-group $ResourceGroup --workspace-name $WorkspaceName --query primarySharedKey --output tsv
```

These commands save the workspace identifier and shared ingestion key into PowerShell variables. The key is sensitive; assignment prevents it from being printed in normal PowerShell output. Do not use `--show-secrets` or print the variable.

```powershell
az containerapp env create --name $EnvironmentName --resource-group $ResourceGroup --location $Location --logs-destination log-analytics --logs-workspace-id $WorkspaceId --logs-workspace-key $WorkspaceKey --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
Remove-Variable WorkspaceKey
```

The first command creates the Container Apps environment and connects its logs to the workspace. This environment is the shared execution boundary for the API and checker job. The second command removes the shared key from the current PowerShell session after setup; it does not revoke the key in Azure.

```powershell
$EnvironmentId = az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup --query id --output tsv
$EnvironmentOutboundIps = @(az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup --query "properties.outboundIpAddresses[]" --output tsv)
$CurrentPublicIp = (Invoke-RestMethod -Uri "https://api4.ipify.org").Trim()
```

These commands retrieve the environment resource ID, the environment's current outbound IP addresses, and this computer's current public IPv4 address. The outbound IPs will be allowed through the PostgreSQL firewall so the API and checker can connect. Azure documents that Container Apps outbound IPs may change; if they do, refresh the database firewall rules. The public IP is used to restrict API ingress to your current network location.

## 5. Create the Registry, Runtime Identity, and Image

```powershell
az acr check-name --name $RegistryName --output table
```

This checks whether the proposed globally unique registry name is available. If it is not, choose a new lowercase alphanumeric `$RegistryName` and repeat the check.

```powershell
az acr create --resource-group $ResourceGroup --name $RegistryName --sku Basic --admin-enabled false --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
```

This creates a private Basic Azure Container Registry. The registry admin account is disabled; the container apps will use managed identity rather than a registry username/password. Basic is a low-tier portfolio default, but verify current regional pricing before creating it.

```powershell
az identity create --resource-group $ResourceGroup --name $IdentityName --location $Location --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
$IdentityId = az identity show --resource-group $ResourceGroup --name $IdentityName --query id --output tsv
$IdentityPrincipalId = az identity show --resource-group $ResourceGroup --name $IdentityName --query principalId --output tsv
$RegistryId = az acr show --resource-group $ResourceGroup --name $RegistryName --query id --output tsv
```

The first command creates a user-assigned managed identity. It is used by the API and checker to pull the private image and by the API to read runtime secrets from Key Vault. The remaining commands retrieve its resource/principal IDs and the registry's resource ID for role assignments.

```powershell
az role assignment create --assignee-object-id $IdentityPrincipalId --assignee-principal-type ServicePrincipal --role AcrPull --scope $RegistryId
```

This grants the identity read-only image-pull permission on this registry. It does not grant permission to push images or manage the registry. Role assignments can take a few minutes to propagate.

```powershell
az acr config authentication-as-arm show --registry $RegistryName --output jsonc
```

This checks whether the registry accepts Microsoft Entra/ARM audience tokens required for managed-identity image pulls. If the output shows that ARM authentication is disabled, enable it with the following command:

```powershell
az acr config authentication-as-arm update --registry $RegistryName --status enabled
```

This enables the token flow used by Container Apps managed identity. Do not enable the ACR admin user as a workaround.

```powershell
az acr build --registry $RegistryName --image "uptime-monitor:$ImageTag" .
```

This sends the current repository build context to Azure Container Registry Tasks, builds the existing `Dockerfile`, and pushes the tagged image. The build runs in Azure, so it does not require a running Docker Desktop daemon on this computer. Run it from the repository root and wait for the task to report success.

```powershell
$AcrLoginServer = az acr show --resource-group $ResourceGroup --name $RegistryName --query loginServer --output tsv
$ImageReference = "${AcrLoginServer}/uptime-monitor:${ImageTag}"
```

These commands capture the registry's actual login server (which can include a generated suffix) and form the immutable image reference used by the API and checker. Verify it with `Write-Output $ImageReference` only; it is not a secret.

## 6. Create PostgreSQL Flexible Server

```powershell
az postgres flexible-server list-skus --location $Location --output table
```

This lists PostgreSQL compute SKUs available in West Europe. Review the available Burstable options and choose the lowest-cost SKU that meets the demo's needs. Confirm its current price and quota in the Azure pricing calculator; do not assume a tier is free or available.

```powershell
$PostgresSku = Read-Host "Enter the lowest suitable available Burstable SKU, for example Standard_B1ms"
```

This records your selected SKU for the create command. The example is illustrative only; use a SKU confirmed by the preceding list and pricing review.

```powershell
az postgres flexible-server create --resource-group $ResourceGroup --name $PostgresServerName --location $Location --admin-user $PostgresAdminUser --admin-password $PostgresAdminPassword --tier Burstable --sku-name $PostgresSku --version 16 --storage-size 32 --backup-retention 7 --geo-redundant-backup Disabled --public-access None --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
```

This provisions PostgreSQL 16 with the selected Burstable compute SKU, the minimum documented 32 GiB storage, seven-day backup retention, and geo-redundant backups disabled. `--public-access None` leaves public networking enabled without adding an allow rule; access remains blocked until the narrow firewall rules below are created. The administrator password is passed from a variable, not hard-coded in command history. Verify provisioning succeeded before continuing.

```powershell
$PostgresFqdn = az postgres flexible-server show --resource-group $ResourceGroup --name $PostgresServerName --query fullyQualifiedDomainName --output tsv
az postgres flexible-server db create --resource-group $ResourceGroup --server-name $PostgresServerName --name $DatabaseName --charset UTF8
```

The first command retrieves the stable DNS hostname for connection strings. The second creates the application's database. Use the FQDN rather than an IP address because Azure may change the server's IP.

```powershell
az postgres flexible-server firewall-rule create --resource-group $ResourceGroup --server-name $PostgresServerName --name allow-deployment-computer --start-ip-address $CurrentPublicIp --end-ip-address $CurrentPublicIp
```

This adds a firewall rule for your current public IPv4 address. It lets the local Alembic command and initial database setup connect from this computer. If your ISP changes your public IP, update this rule before the next local migration.

```powershell
$RuleIndex = 0
foreach ($OutboundIp in $EnvironmentOutboundIps) {
    az postgres flexible-server firewall-rule create --resource-group $ResourceGroup --server-name $PostgresServerName --name "allow-containerapp-$RuleIndex" --start-ip-address $OutboundIp --end-ip-address $OutboundIp
    $RuleIndex++
}
```

This adds one exact-IP firewall rule for each outbound address currently assigned to the Container Apps environment. It is narrower than the `0.0.0.0` rule, which allows connections from all Azure datacenter IPs. The environment's outbound IPs can change; refresh this allowlist if API or checker logs later show PostgreSQL connection timeouts.

## 7. Create the Application Database Role

```powershell
$AdminDatabaseUrl = "postgresql+psycopg://${PostgresAdminUser}:${PostgresAdminPassword}@${PostgresFqdn}:5432/${DatabaseName}?sslmode=require"
$ApplicationDatabaseUrl = "postgresql+psycopg://${ApplicationDbUser}:${ApplicationDbPassword}@${PostgresFqdn}:5432/${DatabaseName}?sslmode=require"
```

These construct TLS-required connection strings for the administrator and the runtime application user. The generated passwords use URL-safe characters, so they do not need percent-encoding. Keep both values in memory only; the administrator URL will be used locally for Alembic, and only the application URL will be given to the API/checker.

```powershell
$env:ADMIN_DATABASE_URL = $AdminDatabaseUrl
$env:APP_DATABASE_PASSWORD = $ApplicationDbPassword
$env:PG_ADMIN_USER = $PostgresAdminUser
```

These environment variables pass credentials to a short Python snippet without embedding them in SQL text or writing them into a repository file. They exist only in this PowerShell process and its child process; clear them immediately after the snippet runs.

```powershell
@'
import os
import psycopg
from psycopg import sql

app_role = sql.Identifier("uptime_monitor")
admin_role = sql.Identifier(os.environ["PG_ADMIN_USER"])

with psycopg.connect(os.environ["ADMIN_DATABASE_URL"]) as connection:
    connection.execute(
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            app_role,
            sql.Literal(os.environ["APP_DATABASE_PASSWORD"]),
        )
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE uptime_monitor TO {}").format(app_role)
    )
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(app_role))
    connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(app_role)
    )
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(app_role)
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(admin_role, app_role)
    )
    connection.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(admin_role, app_role)
    )
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw "Application database role setup failed; do not continue to migrations." }
Remove-Item Env:ADMIN_DATABASE_URL, Env:APP_DATABASE_PASSWORD, Env:PG_ADMIN_USER
```

The Python snippet uses the project's installed `psycopg` driver to connect over TLS and create the `uptime_monitor` role. It grants the API only connection, schema usage, row-level CRUD, and sequence access. Default privileges ensure tables and sequences created by Alembic under the administrator role are usable by the application role. This setup is intended for a new demo database and should not be rerun unchanged if the role already exists. The final commands stop deployment if the role setup failed and clear the temporary credential variables.

## 8. Store Runtime Secrets in Key Vault and Apply Migrations

```powershell
az keyvault create --name $KeyVaultName --resource-group $ResourceGroup --location $Location --enable-rbac-authorization true --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
$KeyVaultId = az keyvault show --name $KeyVaultName --resource-group $ResourceGroup --query id --output tsv
```

The first command creates a Key Vault using Azure RBAC authorization. The second retrieves its resource ID for a narrowly scoped role assignment.

```powershell
az role assignment create --assignee-object-id $IdentityPrincipalId --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KeyVaultId
```

This allows the runtime identity to read secrets from this vault. It does not grant vault administration. Wait a few minutes for the role assignment to propagate before creating or starting the Container Apps resources.

```powershell
$ApplicationDatabaseUrlSecretId = az keyvault secret set --vault-name $KeyVaultName --name app-database-url --value $ApplicationDatabaseUrl --query id --output tsv
$ApiKeySecretId = az keyvault secret set --vault-name $KeyVaultName --name api-key --value $ApiKey --query id --output tsv
```

These commands store the application's PostgreSQL URL and API key in Key Vault, returning each secret's versioned URI into a variable. `--query id` suppresses the secret value from command output. Do not run `az keyvault secret show` with `--query value`, and do not print the PowerShell variables.

```powershell
$PreviousDatabaseUrl = $env:DATABASE_URL
$env:DATABASE_URL = $AdminDatabaseUrl
try {
    & .\.venv\Scripts\python.exe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
}
finally {
    if ($null -eq $PreviousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $PreviousDatabaseUrl
    }
}
```

This runs the repository's checked-in Alembic migrations against Azure PostgreSQL from the local Python virtual environment. No local PostgreSQL server or `psql` installation is needed; the firewall must allow your current IP, and the virtual environment must already have the project dependencies installed. The admin URL is used only for this migration step. The `finally` block restores or removes the temporary environment variable even if a migration fails.

## 9. Deploy the API Container App

The following PowerShell here-string writes a temporary YAML deployment description. It includes the Container Apps environment ID, private image, managed identity, Key Vault secret references, single-replica settings, health checks, and an ingress allowlist for your current IP.

```powershell
$ApiYamlPath = Join-Path $env:TEMP "uptime-api-$Suffix.yaml"
$ApiYaml = @"
location: $Location
name: $ApiAppName
tags:
  project: uptime-monitor
  owner: portfolio-demo
  env: demo
  expires: "$ExpiresOn"
identity:
  type: UserAssigned
  userAssignedIdentities:
    "$IdentityId": {}
properties:
  environmentId: "$EnvironmentId"
  workloadProfileName: Consumption
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      allowInsecure: false
      targetPort: 8000
      transport: auto
      ipSecurityRestrictions:
      - name: allow-owner-current-ip
        description: Allow only the deployment computer's current public IP
        ipAddressRange: "$($CurrentPublicIp)/32"
        action: Allow
    registries:
    - server: "$AcrLoginServer"
      identity: "$IdentityId"
    secrets:
    - name: database-url
      keyVaultUrl: "$ApplicationDatabaseUrlSecretId"
      identity: "$IdentityId"
    - name: api-key
      keyVaultUrl: "$ApiKeySecretId"
      identity: "$IdentityId"
  template:
    containers:
    - name: uptime-api
      image: "$ImageReference"
      command:
      - uvicorn
      args:
      - app.main:app
      - --host
      - 0.0.0.0
      - --port
      - "8000"
      env:
      - name: DATABASE_URL
        secretRef: database-url
      - name: API_KEY
        secretRef: api-key
      - name: LOG_LEVEL
        value: INFO
      resources:
        cpu: 0.25
        memory: 0.5Gi
      probes:
      - type: Startup
        httpGet:
          path: /health
          port: 8000
        initialDelaySeconds: 5
        periodSeconds: 10
        timeoutSeconds: 5
        failureThreshold: 12
      - type: Liveness
        httpGet:
          path: /health
          port: 8000
        periodSeconds: 30
        timeoutSeconds: 5
        failureThreshold: 3
      - type: Readiness
        httpGet:
          path: /ready
          port: 8000
        periodSeconds: 15
        timeoutSeconds: 5
        failureThreshold: 3
    scale:
      minReplicas: 1
      maxReplicas: 1
"@
Set-Content -Path $ApiYamlPath -Value $ApiYaml -Encoding utf8
```

This writes temporary deployment configuration rather than putting credentials into a checked-in file. The YAML itself contains only Key Vault secret URIs and `secretRef` names, never secret values. `/health` is the liveness/startup check; `/ready` confirms the database is reachable. The ingress rule makes the app externally routable but only allows your current IPv4 address. If your public IP changes, update the allow rule before accessing the app again.

```powershell
az containerapp create --resource-group $ResourceGroup --name $ApiAppName --yaml $ApiYamlPath
Remove-Item $ApiYamlPath -Force
```

The first command creates the API app from the YAML, pulls the image using managed identity, resolves its Key Vault references, and exposes ingress on HTTPS while restricting callers to your IP. Wait for provisioning to finish. The second removes the temporary YAML file; it contains no secret values, but should not be kept as a local deployment artifact.

```powershell
$ApiFqdn = az containerapp show --resource-group $ResourceGroup --name $ApiAppName --query properties.configuration.ingress.fqdn --output tsv
Invoke-RestMethod -Uri "https://$ApiFqdn/health"
Invoke-RestMethod -Uri "https://$ApiFqdn/ready"
```

The first command retrieves the generated public hostname. The second should return `status: ok`; the third should return `status: ready`. A 403 or access restriction response usually means the request's current public IP doesn't match the allowlist. A 503 from `/ready` means the API cannot connect to PostgreSQL; check the database firewall, connection URL, and app logs.

## 10. Deploy the Scheduled Checker Job

```powershell
az containerapp job create --name $CheckerJobName --resource-group $ResourceGroup --environment $EnvironmentName --trigger-type Schedule --cron-expression "*/1 * * * *" --replica-timeout 55 --replica-retry-limit 0 --replica-completion-count 1 --parallelism 1 --image $ImageReference --command python --args -m monitor.checker --cpu 0.25 --memory 0.5Gi --registry-server $AcrLoginServer --registry-identity $IdentityId --mi-user-assigned $IdentityId --secrets "database-url=keyvaultref:$ApplicationDatabaseUrlSecretId,identityref:$IdentityId" --env-vars "DATABASE_URL=secretref:database-url" "FAILURE_THRESHOLD=3" "MAX_CONCURRENT_PROBES=20" "DUE_TOLERANCE_SECONDS=5" "MAX_REDIRECTS=0" "RESPONSE_BYTES_LIMIT=1048576" "RETENTION_DAYS=90" "PROBE_USER_AGENT=uptime-monitor-portfolio/1.0" "LOG_LEVEL=INFO" --tags project=uptime-monitor owner=portfolio-demo env=demo expires=$ExpiresOn
```

This creates a scheduled job that runs `python -m monitor.checker` every minute, using the same image, database secret, and managed identity. `--parallelism 1` and `--replica-completion-count 1` keep each execution to one replica; retries are disabled so a failed invocation doesn't silently repeat immediately. The 55-second timeout is intended to keep an execution from occupying the next one-minute interval. Start with a small number of monitors and check execution duration. The current checker does not have the planned PostgreSQL advisory lock, so overlapping runs are not independently serialized; do not scale up monitoring until each run consistently finishes before the next schedule.

```powershell
az containerapp job start --name $CheckerJobName --resource-group $ResourceGroup
```

This starts one immediate execution so you can validate the image, Key Vault access, and database connection without waiting for the next cron tick. The regular schedule remains enabled afterward.

```powershell
az containerapp job execution list --name $CheckerJobName --resource-group $ResourceGroup --query "[].{Name:name, Status:properties.status, Start:properties.startTime}" --output table
```

This lists recent checker executions. Look for a `Succeeded` run. If the job fails, inspect its logs in the Azure portal under the Container Apps environment's Log Analytics workspace; the application writes JSON events to stdout/stderr.

## 11. Verify End-to-End Monitoring

Create a monitor only for a site you are comfortable probing and keep its interval within the project's 1-to-5-minute guidance. For this example, the target is `https://example.com`.

```powershell
$Headers = @{ "X-API-Key" = $ApiKey }
$MonitorBody = @{
    name = "example-site"
    url = "https://example.com"
    expected_status = 200
    interval_seconds = 300
} | ConvertTo-Json
$Monitor = Invoke-RestMethod -Method Post -Uri "https://$ApiFqdn/api/monitors" -Headers $Headers -ContentType "application/json" -Body $MonitorBody
$Monitor
```

The first assignment prepares the required API-key header from the in-memory secret. The next block creates a small JSON request body. `Invoke-RestMethod` sends it to the API's authenticated create endpoint and stores the returned monitor ID in `$Monitor`. The final line displays the monitor response; it contains no API key.

```powershell
Invoke-RestMethod -Uri "https://$ApiFqdn/api/monitors/$($Monitor.id)/results?limit=5"
```

This retrieves recent probe results. After the scheduled job runs, confirm a new result appears with `is_up`, `http_status`, and `latency_ms`. The checker logs also include a structured `monitor.probe.completed` event with the monitor ID and outcome.

## 12. Cost Pause and Cleanup

The demo resources can continue billing while idle, especially PostgreSQL compute and Log Analytics ingestion. Use Azure Cost Management and the pricing calculator during the demo; the budget alert is an alert, not a spending cap. When pausing for a short time, you may stop the database, understanding storage and backup charges can remain:

```powershell
az postgres flexible-server stop --resource-group $ResourceGroup --name $PostgresServerName
```

This stops the database compute. The API and checker will be unable to use the database while it is stopped. Start it again before testing:

```powershell
az postgres flexible-server start --resource-group $ResourceGroup --name $PostgresServerName
```

This restarts PostgreSQL. Wait until the server reports ready before expecting `/ready` or checker executions to succeed.

When the M4 demo is finished and you have saved any screenshots or notes you need, verify that `$ResourceGroup` is the dedicated demo group and contains no unrelated resources. Then, when you are ready to permanently remove the demo:

```powershell
az group delete --name $ResourceGroup --yes
```

This permanently deletes the resource group and every resource inside it, including the database, backups, registry image, Key Vault, and Container Apps. Azure deletion can take several minutes. Do not run this command if the group contains anything you want to keep.

```powershell
az group exists --name $ResourceGroup
```

This verifies cleanup; `false` means the group no longer exists. Check Azure Cost Management again after teardown to confirm no other billable resources were left behind.

## Microsoft References

- [Azure Container Apps scheduled jobs](https://learn.microsoft.com/azure/container-apps/jobs-get-started-cli)
- [Azure Container Apps managed identity image pulls](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull)
- [Azure Container Apps secrets and Key Vault references](https://learn.microsoft.com/azure/container-apps/manage-secrets)
- [Azure Container Apps IP restrictions](https://learn.microsoft.com/azure/container-apps/ip-restrictions)
- [Azure Container Apps networking and outbound IPs](https://learn.microsoft.com/azure/container-apps/networking)
- [Azure PostgreSQL Flexible Server CLI quickstart](https://learn.microsoft.com/azure/postgresql/configure-maintain/quickstart-create-server)
- [Azure PostgreSQL Flexible Server CLI connectivity](https://learn.microsoft.com/azure/postgresql/connectivity/connect-azure-cli)
- [Azure Container Registry CLI quickstart](https://learn.microsoft.com/azure/container-registry/container-registry-get-started-azure-cli)
