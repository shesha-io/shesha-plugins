# Backend API Migration

Phase 2. Expect a **cascade**: each project you fix lets the next one compile and reveal its own errors. Five rounds is normal. Do not estimate from the first error count.

## §1. Configuration Items rewrite

`ConfigurationItemBase` → `ConfigurationItem`, and versioning moved onto `ConfigurationItemRevision`. `VersionNo`, `VersionStatus`, `ParentVersion`, `Origin` and `IsLast` are gone from the item.

### Entity

```csharp
// remove: using Shesha.Domain.ConfigurationItems;
public class {Item} : ConfigurationItem          // was ConfigurationItemBase
{
    public const string ItemTypeName = "{slug}";
    public override string ItemType => ItemTypeName;
    // delete the ctor / Init() that set VersionStatus
}
```

### Manager

`CopyAsync(item, CopyItemInput)` and `CreateNewVersionAsync(item)` both disappear, replaced by one method. The old pair were near-identical bodies that each built the new item by hand and set `Name`/`Module`/`Label`/`VersionNo`/`VersionStatus`/`Origin`/`ParentVersion`; the base class owns all of that now — and owns the repositories, so the constructor injection goes too.

```csharp
public class {Item}Manager : ConfigurationItemManager<{Item}>, I{Item}Manager
{
    // no ctor unless you need extra repositories

    protected override Task CopyItemPropertiesAsync({Item} source, {Item} destination)
    {
        destination.{Prop} = source.{Prop};   // subclass properties only
        return Task.CompletedTask;
    }

    public override Task<IConfigurationItemDto> MapToDtoAsync({Item} item) { ... }
}
```

### Export / Import

```csharp
public class {Item}Export
    : ConfigurableItemExportBase<{Item}, Distributed{Item}>, I{Item}Export, ITransientDependency
{
    public string ItemType => {Item}.ItemTypeName;
    protected override Task MapCustomPropsAsync({Item} item, Distributed{Item} result) { ... }
}

public class {Item}Import
    : ConfigurationItemImportBase<{Item}, Distributed{Item}>, I{Item}Import, ITransientDependency
{
    public {Item}Import(
        IRepository<Module, Guid> moduleRepo,
        IRepository<FrontEndApp, Guid> frontEndAppRepo,
        IRepository<{Item}, Guid> repository
    ) : base(repository, moduleRepo, frontEndAppRepo) { }   // note the argument order

    public override string ItemType => {Item}.ItemTypeName;
    protected override Task<bool> CustomPropsAreEqualAsync({Item} item, Distributed{Item} d) { ... }
    protected override Task MapCustomPropsToItemAsync({Item} item, Distributed{Item} d) { ... }
    protected override Task AfterImportAsync({Item} item, Distributed{Item} d, IConfigurationItemsImportContext ctx) { ... }
}
```

**Key rules:**
- The import base needs `using Shesha.Services.ConfigurationItems;` — without it `ConfigurationItemImportBase<,>` appears missing even though the assembly is referenced.
- The framework now owns item lookup, module resolution, `Normalize()` and JSON serialisation. Delete all of it, including any hand-written `IsLast` query.
- `IsLast` has **no replacement**. It existed only to pick the current row out of sibling version rows; an item is now a single row. Delete the predicate rather than seeking an equivalent, and delete tests that stage superseded siblings — they test a model that no longer exists.
- The `Distributed{Item}` DTO usually needs no change: it declares only custom properties, and the base populates the standard ones.

## §2. Abp 10.3 — `GetAll()` is awaitable

`VSTHRD103` is promoted to an error by `.editorconfig`, so every synchronous `GetAll()` fails the build. Expect 50–100 sites.

**Wrap in place. Do not move the `await`.**

```csharp
X.GetAll()  →  (await X.GetAllAsync())
```

Wrapping preserves any existing outer `await`. *Moving* it silently breaks code that ends in `FirstOrDefaultAsync()`:

```csharp
// WRONG - the variable is now a Task, and .Id resolves to Task.Id (an int)
var m = (await repo.GetAllAsync()).Where(...).FirstOrDefaultAsync();

// RIGHT - both awaits
var m = await (await repo.GetAllAsync()).Where(...).FirstOrDefaultAsync();
```

The compiler catches it only if the result is used in a type-checked position. Two shapes need care:

- **Multiline chains** where `.GetAll()` sits on its own line — the receiver is on the line above; merge them.
- **Methods returning `Task<T>` directly** (no `async`) — add `async` and `return await`.

## §3. Removed and changed APIs

| Was | Now |
|---|---|
| `SendNotificationAsync(..., priority: ...)` | `priority` parameter removed |
| `ShaRoleAppointmentEntity` | removed — usually injected but never read; drop the dependency |
| `Shesha.Web.FormsDesigner.Domain` namespace | gone; `NotificationMessage` via `Shesha.Html.Tools.Message` |
| `protected override void Convert(TextWriter, object)` | log4net widened `PatternConverter.Convert` to `public`; an override cannot narrow |
| `AsyncHelper.RunSync` | still exists, but needs `using Abp.Threading;` |
| `CancellationToken.None` inside a job | the 0.46 job base exposes a `CancellationToken` **property**, which shadows the type name — qualify as `System.Threading.CancellationToken.None` |

**Key rules:**
- Before remapping a removed type, check whether it is actually *used*. `ShaRoleAppointmentEntity` repositories are typically assigned in a constructor and never read — delete rather than substitute.
- Some errors are masked until a blocking project compiles. Rebuild the whole solution after each fix rather than assuming the count is stable.

## §4. Projects outside the .sln

`dotnet build <solution>` reporting 0 errors does **not** mean the backend is clean. Enumerate projects on disk and diff against the solution:

```bash
find . -name '*.csproj' -not -path '*/obj/*' | sort > /tmp/all.txt
grep -oE '[A-Za-z0-9_.\\]+\.csproj' *.sln | tr '\\' '/' | sort -u > /tmp/insln.txt
comm -23 /tmp/all.txt /tmp/insln.txt
```

Test projects are the usual omission. Run them too — a test asserting removed behaviour is a real signal, not noise.

---

## §5. The API root answers 401 instead of redirecting to Swagger

0.46 runs every endpoint through `ObjectPermissionChecker`, including the MVC controllers the
project template generated, and its `!IsAuthenticated` branch rejects the request before the action
runs. A template `HomeController` has no `[AllowAnonymous]`, because it never needed it before.

Put the attribute on the **`Index` action, not the class**. The authorization check accepts it on
either the controller type or the method, and the template controller often holds other actions
(test or diagnostic endpoints) that must stay authenticated — a class-level attribute opens them all.

```csharp
public class HomeController : SheshaControllerBase
{
    [AllowAnonymous]                   // + using Microsoft.AspNetCore.Authorization;
    public IActionResult Index()
    {
        return Redirect("/swagger");
    }
}
```

Seen independently in more than one app, so check for it rather than waiting to be told.

**It hides locally.** A database whose `Shesha.Security` setting has `defaultEndpointAccess = 5`
(anonymous) lets the root through without the attribute, so the defect only appears on environments
using the default (authenticated). Do not judge the attribute unnecessary from a local run.

**Swagger switched off outside Development.** Many apps wrap `UseSwagger()` in `IsDevelopment()`,
while the template `HomeController` still redirects `/` to `/swagger` — so every deployed root lands
on a bare 404 the browser shows as "page can't be found". 0.46 already handles this, driven by the
**Swagger UI Enabled** security setting (`SwaggerUiEnabled`, default `true`):

- `return await RedirectToSwaggerOrDefaultAsync(securitySettings);` in the home action redirects
  when enabled and returns "API is running" when not;
- `SwaggerUiAccessMiddleware` (registered by the app before `UseSwagger`) answers `/swagger` with 403
  when disabled.

Moving to it means turning the setting off on environments that must hide Swagger, because the
default exposes it.

## §6. Front-end applications must be registered

A portal or second front end passing `applicationKey="<key>"` to `ShaApplicationProvider` needs a
matching row in `frwk.front_end_apps`, or form resolution has no registered application to resolve
against. This is easy to miss because it fails quietly and may have been missing for years —
`default-app` is often the only registered key. Add it in an app migration, guarded on the key so
it is safe to re-run.
