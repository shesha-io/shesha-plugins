"""Entity metadata for the rules that need it (url_reflist_columns, readonly_strip, urlfilter).

`properties(ctx, entity_type)` returns the property dicts of `Metadata/Get?entityType=<full class name>` (each has
`path`, `dataType`, `readonly`, `cascadeUpdate`, `entityType`, `referenceListId` ...) or None when the backend does not
know the type. The lookup is lazy and cached for the whole run under the session cache key `metadata:<entityType>`.

Offline tests pre-seed the cache instead of calling a backend:
    session = packs.Session(role='local', options={...}, forms=[...])
    session._cache['metadata:Shop.Domain.Order'] = [{'path': 'Total', 'readonly': True}, ...]   # or None = unknown type
A seeded value is returned as is and no API client is ever created.
"""
import urllib.error

METADATA_PATH = '/api/services/app/Metadata/Get'


def cache_key(entity_type):
    return f'metadata:{entity_type}'


def properties(ctx, entity_type):
    def fetch():
        try:
            return ctx.api().get(METADATA_PATH, entityType=entity_type)['result'].get('properties', [])
        except (urllib.error.URLError, ValueError, KeyError, AttributeError):
            return None     # the backend does not know this type (404 / 400 / not a metadata answer)
    return ctx.cache(cache_key(entity_type), fetch)
