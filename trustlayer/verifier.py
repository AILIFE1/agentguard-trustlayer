"""External provenance verifiers for external_call actions.

The base Verifier in validator.py always returns True (permissive default).
This module provides production-ready subclasses that call external systems
to confirm an action has legitimate provenance before it is applied.

Classes:
    ProvenanceVerifier  abstract base — override verify()
    HttpVerifier        POST action details to any HTTP endpoint
    CathedralVerifier   use Cathedral /verify/external for provenance checks
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from trustlayer.types import Action, ExternalCallConfig
from trustlayer.validator import Verifier


class ProvenanceVerifier(Verifier):
    """Abstract base for verifiers that check external provenance.

    Subclass and implement ``verify(action)`` to gate external_call
    actions against any external source of truth.
    """

    def verify(self, action: Action) -> bool:
        raise NotImplementedError


class HttpVerifier(ProvenanceVerifier):
    """Calls an HTTP endpoint to verify action provenance.

    The verifier POSTs a JSON payload describing the action to
    ``endpoint``. A 2xx response is treated as approval; anything
    else (or a network error) is treated as rejection.

    Payload sent::

        {
          "action_type": "external_call",
          "target": "payment_gateway",
          "endpoint": "https://api.example.com/pay",
          "method": "POST",
          "payload_hash": "<sha256 of action.value.payload>",
          "timestamp": "<iso8601>"
        }

    Example::

        verifier = HttpVerifier(
            endpoint="https://my-audit-service.internal/approve",
            token="Bearer sk-audit-...",
        )
        validator = Validator(state, constraints, secret, verifier=verifier)
    """

    def __init__(
        self,
        endpoint: str,
        token: str = "",
        timeout: int = 5,
    ):
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout

    def verify(self, action: Action) -> bool:
        config = action.value if isinstance(action.value, ExternalCallConfig) else None
        payload: Dict[str, Any] = {
            "action_type": action.type,
            "target": action.target,
        }
        if config:
            payload["endpoint"] = config.endpoint
            payload["method"]   = config.method
            payload["payload_hash"] = hashlib.sha256(
                json.dumps(config.payload, sort_keys=True).encode()
            ).hexdigest()

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = self.token

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status < 300
        except urllib.error.HTTPError as e:
            return False
        except Exception:
            return False


class CathedralVerifier(ProvenanceVerifier):
    """Uses Cathedral /verify/external to check action provenance.

    Calls the Cathedral API's /verify/external endpoint. An
    external_divergence_score below ``max_divergence`` (default 0.3)
    is treated as approval — the action's provenance is consistent
    with the agent's known behavioral baseline.

    Example::

        verifier = CathedralVerifier(
            api_key="cathedral_...",
            agent_id="my-agent",
            max_divergence=0.25,
        )
        validator = Validator(state, constraints, secret, verifier=verifier)
    """

    def __init__(
        self,
        api_key: str,
        agent_id: str = "trustlayer-agent",
        base_url: str = "https://cathedral-ai.com",
        max_divergence: float = 0.3,
        timeout: int = 5,
    ):
        self.api_key = api_key
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.max_divergence = max_divergence
        self.timeout = timeout

    def verify(self, action: Action) -> bool:
        config = action.value if isinstance(action.value, ExternalCallConfig) else None

        summary: Dict[str, Any] = {
            "platform_distribution": [f"trustlayer:1.0"],
            "topic_clusters": [[action.target, action.type]],
            "timing_signatures": [],
            "interaction_ratios": {action.type: 1.0},
        }
        if config:
            summary["topic_clusters"][0].append(config.endpoint)

        payload = json.dumps({
            "ridgeline_summary": summary,
            "agent_id": self.agent_id,
            "action_context": {
                "type": action.type,
                "target": action.target,
            },
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/verify/external",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            score: Optional[float] = data.get("external_divergence_score")
            if score is None:
                return True  # endpoint didn't return a score — allow
            return score <= self.max_divergence
        except Exception:
            return False  # network failure = reject
