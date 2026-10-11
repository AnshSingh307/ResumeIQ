# Deploy ResumeIQ to Azure App Service

This guide separates two valid deployments:

1. **Public fictional demo:** no real applicants, no uploads, isolated seeded data, no login required.
2. **Controlled real-data demonstration:** Microsoft Entra sign-in required, private Blob Storage, one App Service instance, and SQLite persisted under `/home`.

The second mode is intentionally not a scale-out production hiring system. Multiple instances require a managed shared database and a migration away from SQLite.

## 1. Verify the student subscription before spending anything

Sign in to [Azure Portal](https://portal.azure.com/) with the account attached to Azure for Students. Open **Subscriptions** and confirm the subscription is active. Azure's published offer currently describes a time-limited student credit, but service availability and terms can change. In the portal, verify:

- the exact remaining credit and expiry date;
- the displayed monthly price for the chosen Linux App Service plan;
- App Service and Storage availability in the intended region;
- quota and provider registration;
- whether any selected feature remains covered by available credit.

Create a small budget and alerts under **Cost Management + Billing → Budgets** before creating resources. Stop if the portal shows a price you do not accept.

## 2. Prepare GitHub without private data

From the project directory:

```powershell
git init
git status --short
git add .
git status --short
git commit -m "Prepare ResumeIQ for Azure deployment"
git branch -M main
git remote add origin https://github.com/YOUR-USER/YOUR-REPOSITORY.git
git push -u origin main
```

Before `git commit`, confirm that `.env`, `.venv`, `data`, resume files, SQLite files, keys, and certificates are absent from the staged list. Create the empty GitHub repository in your browser first. Use GitHub's credential flow; never paste a personal token into source code or chat.

## 3. Choose the deployment mode

### Option A — public fictional demo

This is the safest public portfolio option. Use `azure/public-demo-settings.example.json`. It disables uploads, deletion, settings changes, and Azure data services. Only bundled fictional records appear.

### Option B — authenticated real-data demonstration

Use `azure/appservice-settings.example.json`. Create:

- one resource group;
- one Linux Web App with a currently supported Python runtime;
- one Storage account with anonymous Blob access disabled;
- one private `resumes` Blob container.

For lowest complexity, keep the Web App at one instance. `/home/data/resumeiq.sqlite3` persists restarts through App Service's persistent content share, but it is not a safe shared database for multiple workers/instances.

Optional Document Intelligence and AI Language resources should be created only after their regional availability and displayed cost are checked. ResumeIQ works without them for text-based PDF/DOCX files.

## 4. Create the Web App

In Azure Portal:

1. Select **Create a resource → Web App**.
2. Choose the verified student subscription and a dedicated resource group.
3. Publish **Code** on **Linux**.
4. Choose a currently supported Python runtime (Python 3.11 when offered).
5. Select the lowest-cost plan that the portal confirms is available and sufficient. Do not assume a free tier.
6. Disable scale-out; keep one instance for the SQLite demonstration architecture.
7. Create the Web App, then enable **HTTPS Only** under its TLS/SSL settings.

Under **Configuration → General settings**, set the startup command:

```text
sh azure/startup.sh
```

The script binds to `0.0.0.0` and `${PORT:-8000}`. App Service build automation installs the root `requirements.txt` when `SCM_DO_BUILD_DURING_DEPLOYMENT=true`.

## 5. Configure persistent data and application settings

Under **Configuration → Application settings**, add the values from the appropriate JSON example. Do not literally use placeholder values.

For the fictional demo, the essential settings are:

```text
RESUMEIQ_ENVIRONMENT=production
RESUMEIQ_DEMO_MODE=true
RESUMEIQ_DEMO_DATA_DIR=/home/demo-data
RESUMEIQ_AUTH_REQUIRED=false
RESUMEIQ_ANONYMOUS_DEFAULT=true
WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

For real data, use:

```text
RESUMEIQ_ENVIRONMENT=production
RESUMEIQ_DEMO_MODE=false
RESUMEIQ_AUTH_REQUIRED=true
RESUMEIQ_ALLOWED_TENANT_ID=<your Entra tenant ID>
RESUMEIQ_DATA_DIR=/home/data
RESUMEIQ_ANONYMOUS_DEFAULT=true
RESUMEIQ_USE_AZURE_BLOB=true
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=resumes
WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

The application refuses to start in real-data production mode when authentication, `/home` persistence, or Blob Storage is not enabled.

On first startup after this feature update, ResumeIQ adds the correction, requirement-version, quality-result, and match-history tables with idempotent `CREATE TABLE IF NOT EXISTS` migrations. It does not replace existing tables or payloads. Back up `/home/data/resumeiq.sqlite3` before every deployment anyway; the migration is additive but a rollback of application code does not remove newer records.

## 6. Configure private Blob Storage with managed identity

For the authenticated mode:

1. In the Web App, open **Identity → System assigned**, switch it **On**, and save.
2. In the Storage account, disable anonymous Blob access and keep the container access level private.
3. Open **Access control (IAM) → Add role assignment**.
4. Assign **Storage Blob Data Contributor** to the Web App's managed identity at the narrowest practical scope (the storage account or container).
5. Set `AZURE_STORAGE_ACCOUNT_URL`; do not set a connection string unless managed identity is unavailable.

Role assignment can take a few minutes to propagate. A 403 generally means identity, scope, networking, or role propagation still needs correction.

## 7. Require Microsoft Entra authentication

For real data:

1. In the Web App, open **Authentication → Add identity provider**.
2. Choose **Microsoft**, create or select the app registration, and require authentication.
3. Set unauthenticated requests to return an HTTP 401 or redirect to sign-in.
4. Limit access to the intended tenant/account population.
5. Set `RESUMEIQ_ALLOWED_TENANT_ID` to that tenant's exact ID.

App Service Authentication validates the identity and supplies the `X-MS-CLIENT-PRINCIPAL` family of headers. ResumeIQ decodes the claims and rejects missing or wrong-tenant identities. Do not expose real candidate data with authentication disabled.

## 8. Connect GitHub and deploy

In the Web App, open **Deployment Center**:

1. Select **GitHub** and authorize only the intended account/repository.
2. Choose the repository and `main` branch.
3. Use the generated GitHub Actions workflow (or App Service build service when offered).
4. Save and watch the first deployment logs.

GitHub Actions credentials belong in GitHub/Azure configuration, never committed files. A successful build is not enough: wait for the deployment and application startup to finish.

## 9. Logging, health, and live verification

Enable **App Service logs** with a short retention appropriate to the demo. Do not log resume text, uploaded bytes, extracted contact details, access tokens, keys, or connection strings.

If the selected plan exposes a health-check setting, use Streamlit's endpoint:

```text
/_stcore/health
```

Then test the Azure-provided HTTPS URL shown on the Web App **Overview** page:

- the health endpoint returns a healthy response;
- Dashboard, Resume Analyzer, Candidates, and Settings load;
- real-data mode redirects unauthenticated users to Microsoft sign-in;
- fictional demo mode exposes only bundled fictional records and no uploader;
- authenticated mode accepts fictional PDF, DOCX, and multi-file uploads;
- anonymous mode, permission-gated audited identity reveal, corrections/reversions, requirement versioning, quality gates, analysis, filters, comparison, sanitized CSV/Excel/JSON downloads, delete confirmation, and restart persistence work;
- Blob objects remain private and deletion removes the corresponding object;
- Log Stream contains no secrets or candidate content.

Only after those checks is the displayed `https://<app-name>.azurewebsites.net` address a verified live URL.

## 10. Redeploy and control costs

With Deployment Center connected, a push to `main` triggers a new deployment:

```powershell
git add .
git commit -m "Describe the ResumeIQ change"
git push
```

Watch the GitHub Actions run and App Service logs, then repeat the health and smoke checks. Keep budget alerts active, review **Cost analysis** regularly, and delete the resource group when the demonstration is over if nothing in it must be retained. Export or deliberately delete candidate data first according to your retention policy.

## Verified platform facts and boundaries

- Azure App Service's Python runtime is Linux-based and supports dependency installation from `requirements.txt` during supported deployments.
- `/home` is the persistent content-share location used for runtime-created persistent files when App Service storage is enabled; temporary filesystem paths are not a persistence strategy.
- App Service Authentication can require Microsoft Entra sign-in and inject authenticated principal headers for the application.
- Azure subscription eligibility, exact plan price, regional resource availability, and remaining student credit are account-specific and must be checked live in the user's portal.

Official references:

- [Azure for Students offer](https://azure.microsoft.com/en-us/pricing/offers/ms-azr-0170p/)
- [Configure Python on Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
- [App Service operating-system and persistent storage behavior](https://learn.microsoft.com/en-us/azure/app-service/operating-system-functionality)
- [Configure Microsoft Entra authentication for App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [Configure a custom startup command for Python](https://learn.microsoft.com/en-us/azure/developer/python/configure-python-web-app-on-app-service)
