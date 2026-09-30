# Local Superset consumer for Lab 11

Run Lab 9's independent case, Lab 10's payment metrics, and then Lab 11. Its explicit `build_payment_dashboard(lab, start=True)` call builds/starts this service, creates a view-only Doris reader, provisions three charts, and verifies real chart-query values. Open the emitted URL to review their rendering and SQL.

- Pinned Superset 4.1.2 and pydoris 1.1.0; native mysqlclient dependencies are built into the image.
- Allow about 2 GiB additional RAM and an internet connection for the first build. The service binds loopback port 51888 only.
- Public **local teaching UI** credentials: `course_admin` / `course_local_only`. The generated Doris reader password is separate and is not displayed.
- SQLite metadata, a fixed teaching secret and HTTP are not a production deployment. Never publish this port on a public interface.
- From the course root, stop without deleting metadata:

```bash
docker compose --project-name doris-warehousing-bi --file environments/bi/compose.yml stop
```

The helper attaches only the course Doris container to this project's network. It does not reconfigure another cluster or grant root to Superset. Rerunning updates the named course objects; the database account and metadata remain until explicitly retired. Do not delete volumes as a routine troubleshooting step.
