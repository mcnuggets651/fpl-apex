from apex.runtime.releases import GitHubReleaseStore


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.pages = {
            1: [{"id": 1}, {"id": 2}],
            2: [{"id": 3}, {"id": 4}],
            3: [{"id": 5}],
        }
        self.calls = []

    def get(self, url, *, headers, params, timeout):
        self.calls.append((url, dict(params)))
        return _Response(self.pages[int(params["page"])])


def test_list_releases_reads_every_page():
    session = _Session()
    store = GitHubReleaseStore("owner/repo", "token", session=session)
    releases = store.list_releases(per_page=2)

    assert [release["id"] for release in releases] == [1, 2, 3, 4, 5]
    assert [call[1]["page"] for call in session.calls] == [1, 2, 3]
