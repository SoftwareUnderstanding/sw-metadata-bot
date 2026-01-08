class RepoAPI:
    token: str = ""

    def __init__(self, token: str = "", dry_run: bool = False) -> None:
        self.token = token
        self.dry_run = dry_run

    @staticmethod
    def get_repo_info(repo_url: str) -> str:
        raise NotImplementedError("This method should be implemented by subclasses.")

    def create_issue(self, repo_url: str, title: str, body: str) -> dict:
        raise NotImplementedError("This method should be implemented by subclasses.")

    def create_pull_request(self, repo_url: str, title: str, body: str, head: str, base: str) -> dict:
        raise NotImplementedError("This method should be implemented by subclasses.")
