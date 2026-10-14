#!/usr/bin/env python3
"""Pre-flight sweep for a Shesha 0.43 -> 0.46 upgrade.

Scans an application repository, without running it, for migration and config-package problems
that otherwise only surface at start-up or on screen.

Usage:
    python preflight_sweep.py <repo-root> [--app-module <Name>] [--all-versions] [--json]

    --app-module    the application's own module name (e.g. Acme.Crm). Package items belonging to
                    other modules are reported, because shipping them does not override the original.
    --all-versions  check every version of each item, not only the latest one shipped.
    --json          machine-readable output.

Standard library only. Package migration numbers are read from the DLLs listed in each
obj/project.assets.json, so run `dotnet restore` first for the clash check to work.
"""
import argparse
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

# --- migrations -------------------------------------------------------------------------------

MIGRATION_FILE = re.compile(r"^M\d{14}\w*\.cs$")
MIGRATION_ATTR = re.compile(r"\[Migration\((\d{14})")
DLL_MIGRATION_NAME = re.compile(rb"M(20\d{12})(?![0-9])")

# Legacy table names and the framework migration that renames them (0 = rename point unknown:
# any reference is worth a look).
LEGACY_TABLES = {
    "Frwk_ConfigurationItems": 20250623120399,
    "Frwk_ReferenceLists": 20250623120399,
    "Frwk_FormConfigurations": 20250623120399,
    "Frwk_Modules": 20250623120399,
    "Frwk_StoredFiles": 20251024104999,
    "Frwk_StoredFileVersions": 20251024104999,
    "Frwk_EntityConfigs": 0,
    "Frwk_EntityProperties": 0,
    "Frwk_SettingValues": 0,
    "Core_NotificationTemplates": 0,
    "Core_NotificationTypeConfigs": 0,
}

# --- config packages --------------------------------------------------------------------------

REMOVED_SETTING_READS = ("azureAdSettings", "sheshaExternalAuthentication")
VERSIONING_FIELDS = re.compile(r"\b(isLast|IsLast|versionStatus|VersionStatus|versionNo|VersionNo)\b")
MOVED_ENTITY_NAMESPACES = ("Shesha.Domain.ConfigurationItems.",)
REMOVED_COMPONENT_TYPES = {"map": "removed in Enterprise 8 (only mapBoundary remains)"}
REMOVED_FORMS = {
    "shesha/roles", "shesha/forms", "shesha/reference-lists", "shesha/scheduled-job",
    "shesha/notification-type-configs", "shesha/notification-channel-configs",
    "shesha.workflow/workflow-definitions",
}
REMOVED_ENDPOINTS = ("ReferenceList/GetByName",)
FLEX_PROPS = ("justifyContent", "flexDirection", "gap", "alignItems", "flexWrap")


def walk_components(components, ancestors=()):
    """Yield (component, ancestor types) for every component, however it is nested."""
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        yield comp, ancestors
        for value in comp.values():
            if isinstance(value, list):
                nested = [v for v in value if isinstance(v, dict)]
                if any("type" in v and "id" in v for v in nested):
                    yield from walk_components(nested, ancestors + (comp.get("type"),))
                else:
                    for item in nested:  # tabs, columns, steps hold components one level down
                        if isinstance(item.get("components"), list):
                            yield from walk_components(item["components"], ancestors + (comp.get("type"),))


def form_refs(value):
    """Yield module/name strings for formId objects anywhere in a value."""
    if isinstance(value, dict):
        if "formId" in value and isinstance(value["formId"], dict):
            fid = value["formId"]
            if fid.get("module") and fid.get("name"):
                yield f"{fid['module']}/{fid['name']}"
        for v in value.values():
            yield from form_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from form_refs(v)


def check_form(markup_text):
    issues = []
    try:
        markup = json.loads(markup_text)
    except (TypeError, ValueError):
        return ["markup is not valid JSON"]

    for needle in REMOVED_SETTING_READS:
        if needle in markup_text:
            issues.append(f"reads removed setting '{needle}' (Azure AD moved to Shesha.MicrosoftAuthentication)")
    fields = sorted(set(VERSIONING_FIELDS.findall(markup_text)))
    if fields:
        issues.append(f"uses configuration-item versioning removed in 0.46: {', '.join(fields)}")
    for ns in MOVED_ENTITY_NAMESPACES:
        if ns in markup_text:
            issues.append(f"references moved entity namespace '{ns}' (now Shesha.Domain)")
    for endpoint in REMOVED_ENDPOINTS:
        if endpoint in markup_text:
            issues.append(f"calls removed endpoint '{endpoint}'")
    for ref in sorted(set(form_refs(markup))):
        if ref.lower() in REMOVED_FORMS:
            issues.append(f"navigates to form '{ref}', removed in 0.46 (Configuration Studio or renamed)")

    for comp, _ in walk_components(markup.get("components")):
        ctype, name = comp.get("type"), comp.get("componentName") or comp.get("propertyName") or comp.get("id")
        if ctype in REMOVED_COMPONENT_TYPES:
            issues.append(f"component '{name}' of type '{ctype}' {REMOVED_COMPONENT_TYPES[ctype]}")
        for key in ("permanentFilter", "filters", "filter"):
            if key in comp and "{{pageContext." in json.dumps(comp[key]):
                issues.append(f"'{name}' filters on {{{{pageContext.…}}}}; set too late for the query in 0.46")
        if ctype == "htmlRender" and "<style" in str(comp.get("renderer", "")) and comp.get("sanitize") is not False:
            issues.append(f"htmlRender '{name}' outputs <style> but is sanitised (Sanitize on)")
        if ctype == "image" and (comp.get("version") or 0) < 6:
            width = (comp.get("desktop") or {}).get("width", comp.get("width"))
            if isinstance(width, str) and re.fullmatch(r"\d+", width) and not (comp.get("desktop") or {}).get("dimensions"):
                issues.append(f"image '{name}' has unitless width '{width}' that the 0.46 migration drops")
        if ctype == "container":
            for bp in ("desktop", "tablet", "mobile"):
                block = comp.get(bp) or {}
                if any(p in block for p in FLEX_PROPS) and block.get("display") != "flex":
                    issues.append(f"container '{name}' {bp} has flex settings without display:flex (flattened)")
                    break
    return issues


def read_package(path):
    """Yield (entry name, item dict) for each JSON item in a .shaconfig."""
    with zipfile.ZipFile(path) as zf:
        for entry in zf.namelist():
            if not entry.lower().endswith(".json"):
                continue
            try:
                item = json.loads(zf.read(entry).decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(item, dict):
                yield entry.replace("\\", "/"), item


def sweep_packages(root, app_module, all_versions):
    packages = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "bin", "obj", ".git", ".next")]
        packages += [os.path.join(dirpath, f) for f in files if f.endswith(".shaconfig")]
    packages.sort(key=os.path.basename)

    latest = {}
    for pkg in packages:
        for entry, item in read_package(pkg):
            key = (item.get("ModuleName"), item.get("ItemType"), item.get("Name"))
            if all_versions:
                latest[(pkg, entry)] = (pkg, entry, item)
            else:
                latest[key] = (pkg, entry, item)

    findings, foreign, roles = defaultdict(list), [], []
    for pkg, entry, item in latest.values():
        module, item_type, name = item.get("ModuleName"), item.get("ItemType"), item.get("Name")
        where = f"{os.path.basename(pkg)} :: {module}/{item_type}/{name}"
        if item_type == "role":
            roles.append(f"{module}/{name}")
        if app_module and module and module != app_module:
            foreign.append(where)
        if item_type == "form":
            markup = item.get("Markup")
            if isinstance(markup, (dict, list)):
                markup = json.dumps(markup)
            for issue in check_form(markup or "{}"):
                findings[where].append(issue)
    return len(packages), dict(findings), foreign, sorted(set(roles))


def package_migration_versions(root):
    """Map migration version -> package name, from DLLs listed in obj/project.assets.json."""
    versions, seen = {}, set()
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", ".next")]
        if "project.assets.json" not in files:
            continue
        with open(os.path.join(dirpath, "project.assets.json"), encoding="utf-8-sig") as fh:
            assets = json.load(fh)
        folders = list((assets.get("packageFolders") or {}).keys())
        for lib_name, lib in (assets.get("libraries") or {}).items():
            if lib.get("type") != "package" or lib_name in seen:
                continue
            seen.add(lib_name)
            for rel in lib.get("files", []):
                if not (rel.startswith("lib/") and rel.endswith(".dll")):
                    continue
                for folder in folders:
                    dll = os.path.join(folder, lib.get("path", ""), rel)
                    if not os.path.isfile(dll):
                        continue
                    data = open(dll, "rb").read()
                    if b"MigrationAttribute" not in data:
                        break
                    for m in DLL_MIGRATION_NAME.finditer(data):
                        versions.setdefault(int(m.group(1)), lib_name.split("/")[0])
                    break
    return versions


def sweep_migrations(root):
    app = defaultdict(list)
    findings = defaultdict(list)
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "bin", "obj", ".git", ".next")]
        for f in files:
            if not MIGRATION_FILE.match(f):
                continue
            path = os.path.join(dirpath, f)
            text = open(path, encoding="utf-8-sig", errors="replace").read()
            m = MIGRATION_ATTR.search(text)
            if not m:
                continue
            version = int(m.group(1))
            rel = os.path.relpath(path, root).replace("\\", "/")
            app[version].append(rel)
            for table, threshold in LEGACY_TABLES.items():
                if table in text and (threshold == 0 or version > threshold):
                    findings[rel].append(f"references legacy table {table}"
                                         + (f" but runs after its rename ({threshold})" if threshold else ""))
            if re.search(r'AddForeignKeyColumn\([^)]*"Frwk_StoredFiles"', text):
                findings[rel].append("AddForeignKeyColumn to Frwk_StoredFiles (cannot name the frwk schema)")
            for table in set(re.findall(r'Create\.Table\("([^"]+)"\)', text)):
                if re.search(r'Schema\.Table\("%s"\)\.(?:Index|Column)' % re.escape(table), text):
                    findings[rel].append(f"guards on Schema.Table(\"{table}\") in the migration that creates it"
                                         " (evaluated before the table exists)")
    duplicates = {v: p for v, p in app.items() if len(p) > 1}
    return app, dict(findings), duplicates


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--app-module")
    ap.add_argument("--all-versions", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    app, mig_findings, duplicates = sweep_migrations(args.root)
    pkg_versions = package_migration_versions(args.root)
    clashes = {v: (app[v], pkg_versions[v]) for v in app if v in pkg_versions}
    pkg_count, form_findings, foreign, roles = sweep_packages(args.root, args.app_module, args.all_versions)

    result = {
        "migrations": {"count": len(app), "duplicate_versions": duplicates,
                       "clash_with_package_migrations": {str(v): {"app": a, "package": p} for v, (a, p) in clashes.items()},
                       "package_migrations_scanned": len(pkg_versions), "findings": mig_findings},
        "packages": {"count": pkg_count, "form_findings": form_findings,
                     "items_of_other_modules": foreign, "roles_shipped": roles},
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"== Migrations: {len(app)} app migrations, {len(pkg_versions)} package migrations scanned")
    if not pkg_versions:
        print("   (no package migrations found - run `dotnet restore` so obj/project.assets.json exists)")
    for v, paths in sorted(duplicates.items()):
        print(f"  DUPLICATE {v}: {', '.join(paths)}")
    for v, (paths, pkg) in sorted(clashes.items()):
        print(f"  CLASH {v}: {', '.join(paths)} <-> package {pkg}  (DuplicateMigrationException at start-up)")
    for path, issues in sorted(mig_findings.items()):
        for issue in issues:
            print(f"  {path}: {issue}")

    print(f"\n== Config packages: {pkg_count} packages")
    for where, issues in sorted(form_findings.items()):
        print(f"  {where}")
        for issue in issues:
            print(f"      - {issue}")
    if foreign:
        print(f"\n  Items of other modules shipped by the app ({len(foreign)}): they arrive as separate items,"
              " not overrides - expose them in code before import:")
        for where in foreign:
            print(f"      {where}")
    if roles:
        print(f"\n  Roles shipped ({len(roles)}) - check none is soft-deleted in the target database:")
        print("      " + ", ".join(roles))


if __name__ == "__main__":
    sys.exit(main())
