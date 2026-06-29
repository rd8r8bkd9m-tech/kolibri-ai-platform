# GitHub API inventory для фабрики Kolibri

Роль: `github_api_inventory_operator`

Дата проверки: 2026-06-29, Europe/Moscow.

Репозиторий:

```text
rd8r8bkd9m-tech/kolibri-ai-platform
```

Матрица описывает текущий гибридный контур: локальный GitHub CLI `gh` 2.83.1
и доступные GitHub plugin wrapper'ы Codex. Новые токены не нужны и не
запрашиваются. Текущий `gh auth status` показывает scopes:

```text
gist, project, read:org, repo, user, workflow
```

GitHub Project, issues, PR и CI остаются внешним операционным экраном фабрики.
Control Plane остается источником факта по `task_id`, lease, runtime state,
результатам и artifact manifest. В GitHub переносится только безопасная
выжимка и ссылки на проверяемые артефакты.

## Базовые правила

- Чтение можно автоматизировать, если вывод не содержит секретов, приватных
  логов, персональных данных третьих лиц и локальных auth/cache путей.
- Запись разрешена только в рамках явной задачи: issue/PR report, Project sync,
  label/status update или CI blocker report.
- Разрушительные, публичные, массовые или permission-changing действия требуют
  отдельного подтверждения владельца.
- Не запускать `gh auth refresh`, не создавать PAT, fine-grained token, OAuth
  token или GitHub App token из агентной автоматизации.
- Для `gh api` использовать `--jq` или узкие endpoints, чтобы не печатать
  лишние поля в логи.
- Plugin и `gh` могут видеть разные множества репозиториев: plugin ограничен
  установкой GitHub App, `gh` ограничен scopes текущего аккаунта.

## Матрица capability

| Capability | Endpoint / `gh` / plugin wrapper | Scope | Что автоматизировать для фабрики | Ограничения и риски | Нельзя без дополнительного подтверждения |
| --- | --- | --- | --- | --- | --- |
| Repos | REST: `GET /repos/{owner}/{repo}`, `GET /user/repos`, `GET /installation/repositories`.<br>`gh`: `gh repo view`, `gh repo list`, `gh api repos/$KOLIBRI_REPO`.<br>Plugin: `_list_repositories`, `_list_repositories_by_installation`, `_search_installed_repositories_v2`, `_get_repo_collaborator_permission`. | `repo` для private repo; `read:org` для org context; GitHub App installation определяет plugin-доступ. | Preflight доступа агента; определение default branch; проверка прав перед PR/Project sync; инвентаризация доступных repo для маршрутизации задач. | Metadata приватных repo может раскрывать roadmap; plugin и `gh` могут расходиться по permissions; search может не видеть repo вне installation. | Создавать, архивировать, удалять, transfer repo; менять visibility, settings, collaborators, topics, branch protection или default branch. |
| Issues | REST: `GET/POST/PATCH /repos/{owner}/{repo}/issues`, `GET/POST /repos/{owner}/{repo}/issues/{issue_number}/comments`.<br>`gh`: `gh issue list`, `view`, `create`, `edit`, `comment`, `close`, `reopen`.<br>Plugin: `_search_issues`, `_fetch_issue_comments`, `_update_issue`, `_add_comment_to_issue`, issue comment reactions. | `repo`. | Создавать GitHub-visible follow-up для Control Plane tasks; писать blocker report; обновлять status/comment; связывать issue с PR и artifact manifest; искать незакрытые долги. | `update_issue(labels=...)` заменяет полный набор labels; issue comments публично шумят в thread; body может случайно раскрыть приватные runtime details. | Закрывать/переоткрывать чужие issue; массово создавать issue; заменять title/body/labels/assignees/milestone без явного owner/task context; публиковать raw logs, secrets или персональные данные. |
| Pull Requests | REST: `GET/POST/PATCH /repos/{owner}/{repo}/pulls`, review/comment endpoints, GraphQL review threads.<br>`gh`: `gh pr list`, `view`, `create`, `edit`, `comment`, `review`, `ready`, `merge`, `status`.<br>Plugin: `_get_pr_info`, `_fetch_pr`, `_fetch_pr_comments`, `_list_pull_request_review_threads`, `_list_pull_request_reviews`, `_add_review_to_pr`, `_update_pull_request`, `_mark_pull_request_ready_for_review`, reviewer request tools. | `repo`. | Находить PR текущей ветки; собирать diff/comment context для review; добавлять безопасные status comments; проверять draft/ready state; связывать PR с Control Plane task и CI. | Review actions необратимо видны участникам; `APPROVE`/`REQUEST_CHANGES` меняют review semantics; retarget base может изменить diff; merge может закрыть issue через keywords. | Merge/squash/rebase; закрывать или reopen PR; переводить draft в ready; approve/request changes/dismiss review; менять base branch; запрашивать или снимать reviewers; публиковать большой generated diff без PR context. |
| Labels | REST: `GET/POST/PATCH/DELETE /repos/{owner}/{repo}/labels`, `POST/DELETE /issues/{issue_number}/labels`.<br>`gh`: `gh label list/create/edit/delete`, `gh issue edit --add-label/--remove-label`.<br>Plugin: `_add_issue_labels`, `_remove_issue_label`, `_label_pr`, `_update_issue(labels=...)`. | `repo`. | Ставить направление, приоритет, CI/blocker и factory labels; поддерживать taxonomy для issue/PR triage; помечать задачи, пришедшие из Control Plane. | Глобальная label taxonomy влияет на весь repo; replacement labels могут стереть чужие labels; удаление labels ломает историческую фильтрацию. | Создавать/удалять/переименовывать repository labels; массово relabel; снимать labels, поставленные reviewer/owner; заменять полный label set без diff-check. |
| Projects v2 | GraphQL: `ProjectV2`, `ProjectV2Item`, `addProjectV2ItemById`, `updateProjectV2ItemFieldValue`.<br>`gh`: `gh project list`, `view`, `item-add`, `item-list`, `field-list`, `item-edit`.<br>Plugin: отдельного Project v2 writer wrapper в текущем списке не видно; использовать `gh project` или `gh api graphql`. | `project`; для org-owned Project также `read:org`; repo/issue/PR операции требуют `repo`. | Синхронизировать issue/PR с Project; обновлять `Статус`, `Приоритет`, `Направление`, `Агент`, `Следующий отчёт`, `Артефакты`; оставлять `Project sync: pending`, если IDs или scope недоступны. | CLI требует project number, project node id, item id, field id и option id; GraphQL IDs хрупкие для ручных шаблонов; Project не является источником факта для runtime state. | Создавать/удалять Project; менять schema fields/options; архивировать/удалять items; массово переводить статусы; ставить `Готово` без acceptance, artifact и PR/issue trail. |
| Actions / workflow | REST: `GET /repos/{owner}/{repo}/actions/runs`, jobs, logs, artifacts, rerun endpoints.<br>`gh`: `gh run list`, `gh run view --log-failed`, `gh run rerun`, `gh workflow list`, `gh workflow run`.<br>Plugin: `_fetch_commit_workflow_runs`, `_fetch_workflow_run_jobs`, `_fetch_workflow_job_steps`, `_fetch_workflow_job_logs`, `_fetch_workflow_run_artifacts`, `_download_workflow_artifact`, rerun tools. | `workflow` plus `repo` for private repo. | Мониторить CI текущих PR; забирать failed logs; писать root-cause summary; скачивать безопасные artifacts; формировать blocker report; проверять auto-fix результат. | Logs могут содержать paths, env names и случайные secrets; artifact ZIP может быть большим или содержать приватные данные; first-page wrappers могут не вернуть все runs/jobs. | Триггерить workflow dispatch; rerun/cancel jobs; enable/disable workflows; approve deployments; удалять logs/artifacts; менять workflow files или GitHub Actions secrets. |
| Contents | REST: `GET/PUT/DELETE /repos/{owner}/{repo}/contents/{path}`, Git blobs/trees/commits refs.<br>`gh`: `gh api repos/$KOLIBRI_REPO/contents/...`, обычный `git` для local branch flow.<br>Plugin: `_fetch_file`, `_create_file`, `_update_file`, `_delete_file`, `_fetch_blob`, `_create_blob`. | `repo`. | Читать docs/configs для агентов; публиковать небольшие generated reports только в dedicated branch; сверять remote file SHA перед update; сохранять markdown artifacts рядом с PR. | Contents API создает commit сразу на выбранной ветке; default branch write опасен; `sha` должен быть актуальным; легко опубликовать local-only paths или secrets. | Писать или удалять файлы на default/protected branch; менять `.github/workflows`, security/config files, license или owner-facing docs без review; публиковать raw node artifacts; коммитить бинарные/большие файлы через API. |
| Branches | REST/Git: `GET /repos/{owner}/{repo}/branches`, `GET/POST/PATCH/DELETE /git/refs/heads/{branch}`.<br>`gh`: `gh api repos/$KOLIBRI_REPO/git/ref/heads/...`; локально `git switch -c`, `git push`.<br>Plugin: `_search_branches`, `_create_branch`, `_update_ref`. | `repo`. | Проверять наличие task branch; создавать `codex/<slug>` или `agent/<TASK_ID>/<slug>`; находить PR branch; обновлять refs только после локальной проверки и явного push flow. | `update_ref(force=true)` переписывает историю; branch name collisions путают агентов; protected branches могут отклонять push; plugin create branch не создает commits. | Force update/force push; удалять branches; менять protected/default branch; пушить в чужую branch namespace; создавать branch от непроверенного SHA. |
| Profile / user | REST: `GET /user`, `GET /users/{username}`.<br>`gh`: `gh api user`, `gh auth status`.<br>Plugin: `_get_user_login`, `_get_profile`. | `user`; часть public profile доступна без private scope. | Привязать operator login к audit trail; проверить активный аккаунт перед `gh` write; формировать безопасный GitHub profile README draft без приватных данных. | Profile может содержать email, location, social links; `gh auth status` показывает masked token prefix и scopes; не логировать auth internals шире, чем нужно. | Менять profile, email, keys, auth settings; запускать `gh auth refresh/login`; публиковать приватные profile details; связывать личность агента с внешними claims без owner context. |
| Org read | REST: `GET /user/orgs`, `GET /orgs/{org}`, `GET /user/memberships/orgs`.<br>`gh`: `gh api user/orgs`, `gh api user/memberships/orgs`.<br>Plugin: `_list_user_orgs`, `_list_user_org_memberships`, `_list_installations`, `_list_installed_accounts`. | `read:org`; plugin visibility зависит от GitHub App installation. | Определять owner для Project v2; проверять installation/repo visibility; маршрутизировать tasks по org/repo; диагностировать `Project sync: pending` из-за owner/scope mismatch. | Private org membership является чувствительной информацией; org role не равен repo permission; installation list может раскрывать private operational footprint. | Публиковать приватные org memberships; приглашать/удалять members; менять teams, org settings, repo access, billing или app installation. |
| Gists | REST: `GET/POST/PATCH/DELETE /gists`, gist comments.<br>`gh`: `gh gist list`, `view`, `create`, `edit`, `delete`.<br>Plugin: отдельного gist wrapper в текущем списке не видно; использовать `gh gist` или `gh api gists` при явном разрешении. | `gist`. | В штатном factory flow не использовать. Допустимый редкий сценарий: временный sanitized snippet без секретов, если owner явно попросил gist вместо repo artifact. | Gist легко сделать public/unlisted и утечь за пределы repo governance; lifecycle и review слабее, чем у PR artifacts; raw logs часто содержат чувствительные строки. | Создавать, редактировать, удалять или публиковать gist; переносить туда logs, artifacts, config, env, stack traces, customer data или приватные server details. |

## Рекомендуемый безопасный контур автоматизации

1. `gh auth status` только для проверки account/scopes, без печати token value.
2. `gh pr status`, `gh pr view`, `gh run list`, `gh run view --log-failed`
   для диагностики текущей ветки и CI.
3. Plugin wrappers для structured PR/issue review context, если нужен
   нормализованный diff/comment/thread payload.
4. `gh issue create/comment` или `gh pr comment` для безопасного status report.
5. `gh project item-add/item-edit` только после определения Project IDs и
   field IDs; при ошибке писать `Project sync: pending`.
6. Любые writes сначала в dedicated branch/PR, затем CI, review и merge.

## Красные линии

- Не создавать новые токены и не расширять scopes из агентного процесса.
- Не выводить secrets, auth files, env dumps, cookies, private keys, raw
  OAuth/cache files.
- Не использовать gists как замену PR artifacts.
- Не выполнять destructive GitHub API действия без отдельного подтверждения.
- Не считать Project v2 источником факта по состоянию фабрики: сверяться с
  Control Plane и artifact manifest.
