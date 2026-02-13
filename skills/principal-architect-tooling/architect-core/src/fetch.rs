//! Metadata fetchers for API-first and fallback research.

use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::time::Duration;

use regex::Regex;
use reqwest::blocking::{Client, Response};
use reqwest::header::{ACCEPT, AUTHORIZATION, USER_AGENT, WWW_AUTHENTICATE};
use serde::Deserialize;
use serde_json::Value;
use url::Url;

use crate::error::AppError;
use crate::model::{ImageProfile, Platform};

#[derive(Debug, Clone)]
struct ParsedImageRef {
    registry: String,
    repository: String,
    reference: String,
    normalized: String,
    tag: String,
}

#[derive(Debug)]
struct AuthChallenge {
    realm: String,
    service: Option<String>,
    scope: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DockerHubTagResponse {
    images: Vec<DockerHubTagImage>,
}

#[derive(Debug, Deserialize)]
struct DockerHubTagImage {
    architecture: Option<String>,
    os: Option<String>,
    digest: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DockerHubRepoResponse {
    full_description: Option<String>,
}

#[derive(Debug)]
struct DockerHubMetadata {
    digest: Option<String>,
    platforms: Vec<Platform>,
    docs_url: Option<String>,
    dockerfile_url: Option<String>,
}

/// Fetch one image profile.
///
/// # Arguments
/// * `image` - Image reference containing name and optional tag.
/// * `allow_scrape_fallback` - Whether HTML fallback is enabled.
///
/// # Returns
/// * `Ok(ImageProfile)` when metadata is resolved.
/// * `Err(AppError)` when both API and fallback fail.
///
/// # Examples
/// ```no_run
/// use architect_core::fetch::fetch_image_profile;
///
/// let profile = fetch_image_profile("nginx:1.27", true, "agent-skills-pca/0.1")?;
/// assert!(profile.image.contains("nginx"));
/// # Ok::<(), architect_core::error::AppError>(())
/// ```
pub fn fetch_image_profile(
    image: &str,
    allow_scrape_fallback: bool,
    user_agent: &str,
) -> Result<ImageProfile, AppError> {
    let client = Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|error| AppError::InvalidInput {
            reason: format!("failed to build http client: {error}"),
        })?;

    let parsed = parse_image_reference(image)?;
    let mut notes = Vec::new();

    let mut digest: Option<String> = if is_digest_reference(&parsed.reference) {
        Some(parsed.reference.clone())
    } else {
        None
    };
    let mut platforms: Vec<Platform> = Vec::new();
    let mut docs_url: Option<String> = None;
    let mut dockerfile_url: Option<String> = None;

    if parsed.registry == "docker.io" {
        match fetch_docker_hub_metadata(&client, &parsed, user_agent) {
            Ok(hub) => {
                if digest.is_none() {
                    digest = hub.digest;
                }
                platforms = hub.platforms;
                docs_url = hub.docs_url;
                dockerfile_url = hub.dockerfile_url;
                notes.push("source:docker-hub-api".to_string());
            }
            Err(error) => {
                notes.push(format!("docker-hub-api-failed:{error}"));
            }
        }
    }

    if digest.is_none() || platforms.is_empty() {
        match fetch_registry_manifest(&client, &parsed, user_agent) {
            Ok((manifest_digest, manifest_platforms)) => {
                if digest.is_none() {
                    digest = manifest_digest;
                }
                if platforms.is_empty() {
                    platforms = manifest_platforms;
                }
                notes.push("source:registry-v2".to_string());
            }
            Err(error) => {
                notes.push(format!("registry-v2-failed:{error}"));
            }
        }
    }

    if allow_scrape_fallback
        && parsed.registry == "docker.io"
        && (digest.is_none() || dockerfile_url.is_none())
    {
        if let Ok((scraped_digest, scraped_repo_url)) =
            scrape_hub_page(&client, &parsed.repository, user_agent)
        {
            if digest.is_none() {
                digest = scraped_digest;
            }
            if dockerfile_url.is_none() {
                dockerfile_url = scraped_repo_url;
            }
            notes.push("source:html-fallback".to_string());
        }
    }

    if docs_url.is_none() {
        docs_url = infer_docs_url(&parsed);
        if docs_url.is_some() {
            notes.push("source:docs-heuristic".to_string());
        }
    }

    Ok(ImageProfile {
        id: String::new(),
        image: parsed.normalized,
        docs_url,
        dockerfile_url,
        digest,
        platforms,
        notes,
    })
}

/// Fetch multiple profiles preserving deterministic order.
///
/// # Arguments
/// * `images` - Normalized image references.
/// * `allow_scrape_fallback` - Enables HTML fallback.
///
/// # Returns
/// * `Ok(Vec<ImageProfile>)` ordered by input.
///
/// # Examples
/// ```no_run
/// use architect_core::fetch::fetch_profiles;
///
/// let profiles = fetch_profiles(&["nginx:1.27".to_string()], true, "agent-skills-pca/0.1")?;
/// assert_eq!(profiles.len(), 1);
/// # Ok::<(), architect_core::error::AppError>(())
/// ```
pub fn fetch_profiles(
    images: &[String],
    allow_scrape_fallback: bool,
    user_agent: &str,
) -> Result<Vec<ImageProfile>, AppError> {
    let mut output = Vec::with_capacity(images.len());
    for image in images {
        output.push(fetch_image_profile(
            image,
            allow_scrape_fallback,
            user_agent,
        )?);
    }
    Ok(output)
}

fn fetch_docker_hub_metadata(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
) -> Result<DockerHubMetadata, AppError> {
    let (digest, platforms) = if is_digest_reference(&parsed.reference) {
        (None, Vec::new())
    } else {
        fetch_docker_hub_tag_metadata(client, parsed, user_agent)?
    };
    let dockerfile_url = fetch_docker_hub_repo_dockerfile_url(client, parsed, user_agent)?;

    Ok(DockerHubMetadata {
        digest,
        platforms,
        docs_url: Some(format!("https://hub.docker.com/r/{}", parsed.repository)),
        dockerfile_url,
    })
}

fn fetch_docker_hub_tag_metadata(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
) -> Result<(Option<String>, Vec<Platform>), AppError> {
    let tag_url = format!(
        "https://hub.docker.com/v2/repositories/{}/tags/{}",
        parsed.repository, parsed.tag
    );
    let tag_response = client
        .get(&tag_url)
        .header(USER_AGENT, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: tag_url.clone(),
            reason: error.to_string(),
        })?;

    if !tag_response.status().is_success() {
        return Err(AppError::Http {
            url: tag_url.clone(),
            reason: format!("unexpected status {}", tag_response.status()),
        });
    }

    let tag_payload: DockerHubTagResponse =
        tag_response.json().map_err(|error| AppError::Http {
            url: tag_url.clone(),
            reason: format!("invalid docker hub tag payload: {error}"),
        })?;

    let mut platforms = Vec::new();
    let mut digest = None;
    for image in tag_payload.images {
        if digest.is_none() {
            digest = image.digest.clone();
        }

        if let (Some(os), Some(arch)) = (image.os, image.architecture) {
            if os != "unknown" && arch != "unknown" {
                platforms.push(Platform { os, arch });
            }
        }
    }

    Ok((digest, platforms))
}

fn fetch_docker_hub_repo_dockerfile_url(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
) -> Result<Option<String>, AppError> {
    let repo_url = format!(
        "https://hub.docker.com/v2/repositories/{}",
        parsed.repository
    );
    let repo_response = client
        .get(&repo_url)
        .header(USER_AGENT, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: repo_url.clone(),
            reason: error.to_string(),
        })?;

    if !repo_response.status().is_success() {
        return Ok(None);
    }

    let repo_payload: DockerHubRepoResponse =
        repo_response.json().map_err(|error| AppError::Http {
            url: repo_url,
            reason: format!("invalid docker hub repository payload: {error}"),
        })?;

    Ok(repo_payload
        .full_description
        .as_deref()
        .and_then(extract_github_url))
}

fn infer_docs_url(parsed: &ParsedImageRef) -> Option<String> {
    if parsed.registry == "docker.io" {
        return Some(format!("https://hub.docker.com/r/{}", parsed.repository));
    }

    if parsed.registry == "quay.io" {
        return Some(format!("https://quay.io/repository/{}", parsed.repository));
    }

    if parsed.registry == "ghcr.io" {
        let mut parts = parsed.repository.split('/');
        if let (Some(owner), Some(repo)) = (parts.next(), parts.next()) {
            return Some(format!("https://github.com/{owner}/{repo}"));
        }
    }

    None
}

fn fetch_registry_manifest(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
) -> Result<(Option<String>, Vec<Platform>), AppError> {
    let manifest_url = format!(
        "https://{}/v2/{}/manifests/{}",
        parsed.registry, parsed.repository, parsed.reference
    );

    let response = request_registry_with_auth(client, parsed, &manifest_url, user_agent)?;
    parse_manifest_response(client, parsed, user_agent, &manifest_url, response)
}

fn parse_manifest_response(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
    url: &str,
    response: Response,
) -> Result<(Option<String>, Vec<Platform>), AppError> {
    if !response.status().is_success() {
        return Err(AppError::Http {
            url: url.to_string(),
            reason: format!("unexpected status {}", response.status()),
        });
    }

    let digest = response
        .headers()
        .get("Docker-Content-Digest")
        .and_then(|value| value.to_str().ok())
        .map(ToOwned::to_owned);

    let value: Value = response.json().map_err(|error| AppError::Http {
        url: url.to_string(),
        reason: format!("manifest payload parse failed: {error}"),
    })?;

    let mut platforms = Vec::new();
    if let Some(manifests) = value.get("manifests").and_then(Value::as_array) {
        for manifest in manifests {
            let os = manifest
                .get("platform")
                .and_then(|platform| platform.get("os"))
                .and_then(Value::as_str);
            let arch = manifest
                .get("platform")
                .and_then(|platform| platform.get("architecture"))
                .and_then(Value::as_str);
            if let (Some(os), Some(arch)) = (os, arch) {
                platforms.push(Platform {
                    os: os.to_string(),
                    arch: arch.to_string(),
                });
            }
        }
    } else if let Some(config_digest) = value
        .get("config")
        .and_then(|config| config.get("digest"))
        .and_then(Value::as_str)
    {
        if let Some(platform) =
            fetch_config_blob_platform(client, parsed, config_digest, user_agent)?
        {
            platforms.push(platform);
        }
    }

    Ok((digest, platforms))
}

fn fetch_config_blob_platform(
    client: &Client,
    parsed: &ParsedImageRef,
    config_digest: &str,
    user_agent: &str,
) -> Result<Option<Platform>, AppError> {
    let blob_url = format!(
        "https://{}/v2/{}/blobs/{}",
        parsed.registry, parsed.repository, config_digest
    );
    let response = request_registry_with_auth(client, parsed, &blob_url, user_agent)?;
    if !response.status().is_success() {
        return Ok(None);
    }

    let value: Value = response.json().map_err(|error| AppError::Http {
        url: blob_url.clone(),
        reason: format!("config blob parse failed: {error}"),
    })?;

    Ok(extract_platform_from_config_payload(&value))
}

fn request_registry(
    client: &Client,
    url: &str,
    token: Option<&str>,
    user_agent: &str,
) -> Result<Response, AppError> {
    let mut request = client
        .get(url)
        .header(USER_AGENT, user_agent)
        .header(
            ACCEPT,
            "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json",
        );

    if let Some(value) = token {
        request = request.header(AUTHORIZATION, format!("Bearer {value}"));
    }

    request.send().map_err(|error| AppError::Http {
        url: url.to_string(),
        reason: error.to_string(),
    })
}

fn request_registry_with_auth(
    client: &Client,
    parsed: &ParsedImageRef,
    url: &str,
    user_agent: &str,
) -> Result<Response, AppError> {
    let response = request_registry(client, url, None, user_agent)?;
    if response.status() != reqwest::StatusCode::UNAUTHORIZED {
        return Ok(response);
    }

    let challenge = response
        .headers()
        .get(WWW_AUTHENTICATE)
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| AppError::Http {
            url: url.to_string(),
            reason: "registry returned 401 without WWW-Authenticate".to_string(),
        })?;

    let auth = parse_auth_challenge(challenge).ok_or_else(|| AppError::Http {
        url: url.to_string(),
        reason: "failed to parse auth challenge".to_string(),
    })?;

    let token = fetch_bearer_token(
        client,
        &auth,
        &parsed.repository,
        &parsed.registry,
        user_agent,
    )?;
    request_registry(client, url, Some(&token), user_agent)
}

fn fetch_bearer_token(
    client: &Client,
    challenge: &AuthChallenge,
    repository: &str,
    registry: &str,
    user_agent: &str,
) -> Result<String, AppError> {
    let mut token_url = validate_realm_url(&challenge.realm, registry)?;

    {
        let mut query = token_url.query_pairs_mut();
        if let Some(service) = challenge.service.as_deref() {
            query.append_pair("service", service);
        }

        let scope = challenge
            .scope
            .as_deref()
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| format!("repository:{repository}:pull"));
        query.append_pair("scope", &scope);
    }

    let url_string = token_url.to_string();
    let response = client
        .get(token_url)
        .header(USER_AGENT, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: url_string.clone(),
            reason: error.to_string(),
        })?;

    if !response.status().is_success() {
        return Err(AppError::Http {
            url: url_string,
            reason: format!("unexpected status {}", response.status()),
        });
    }

    let payload: Value = response.json().map_err(|error| AppError::Http {
        url: url_string.clone(),
        reason: format!("token payload parse failed: {error}"),
    })?;

    payload
        .get("token")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .ok_or_else(|| AppError::Http {
            url: challenge.realm.clone(),
            reason: "token response did not include token field".to_string(),
        })
}

fn validate_realm_url(realm: &str, registry: &str) -> Result<Url, AppError> {
    let url = Url::parse(realm).map_err(|error| AppError::Http {
        url: realm.to_string(),
        reason: format!("invalid token realm url: {error}"),
    })?;

    if url.scheme() != "https" {
        return Err(AppError::Http {
            url: realm.to_string(),
            reason: "token realm url must use https".to_string(),
        });
    }

    let realm_host = url.host_str().ok_or_else(|| AppError::Http {
        url: realm.to_string(),
        reason: "token realm url did not include a host".to_string(),
    })?;

    let registry_host = Url::parse(&format!("https://{registry}"))
        .map_err(|error| AppError::Http {
            url: registry.to_string(),
            reason: format!("invalid registry host: {error}"),
        })?
        .host_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| AppError::Http {
            url: registry.to_string(),
            reason: "registry host resolution failed".to_string(),
        })?;

    if !is_same_or_subdomain(realm_host, &registry_host) {
        return Err(AppError::Http {
            url: realm.to_string(),
            reason: format!(
                "token realm host {realm_host} is not in registry domain {registry_host}"
            ),
        });
    }

    if is_disallowed_host(realm_host) {
        return Err(AppError::Http {
            url: realm.to_string(),
            reason: format!("token realm host {realm_host} is not allowed"),
        });
    }

    Ok(url)
}

fn is_same_or_subdomain(candidate: &str, registry_host: &str) -> bool {
    let candidate_lower = candidate.to_ascii_lowercase();
    let registry_lower = registry_host.to_ascii_lowercase();
    candidate_lower == registry_lower || candidate_lower.ends_with(&format!(".{registry_lower}"))
}

fn is_disallowed_host(host: &str) -> bool {
    if host.eq_ignore_ascii_case("localhost") {
        return true;
    }

    if let Ok(ip) = host.parse::<IpAddr>() {
        return match ip {
            IpAddr::V4(value) => is_disallowed_ipv4(value),
            IpAddr::V6(value) => is_disallowed_ipv6(value),
        };
    }

    false
}

fn is_disallowed_ipv4(value: Ipv4Addr) -> bool {
    value.is_private()
        || value.is_loopback()
        || value.is_link_local()
        || value.is_broadcast()
        || value.is_documentation()
        || value.is_multicast()
        || value.is_unspecified()
}

fn is_disallowed_ipv6(value: Ipv6Addr) -> bool {
    value.is_loopback()
        || value.is_unspecified()
        || value.is_multicast()
        || value.is_unique_local()
        || value.is_unicast_link_local()
        || value.segments()[0] == 0x2001 && value.segments()[1] == 0x0db8
}

fn parse_auth_challenge(value: &str) -> Option<AuthChallenge> {
    let lower = value.to_ascii_lowercase();
    if !lower.starts_with("bearer ") {
        return None;
    }

    let params = value.split_once(' ')?;
    let mut realm = None;
    let mut service = None;
    let mut scope = None;

    for part in params.1.split(',') {
        let (key, raw) = part.trim().split_once('=')?;
        let parsed = raw.trim().trim_matches('"').to_string();
        match key {
            "realm" => realm = Some(parsed),
            "service" => service = Some(parsed),
            "scope" => scope = Some(parsed),
            _ => {}
        }
    }

    Some(AuthChallenge {
        realm: realm?,
        service,
        scope,
    })
}

fn scrape_hub_page(
    client: &Client,
    repository: &str,
    user_agent: &str,
) -> Result<(Option<String>, Option<String>), AppError> {
    let url = format!("https://hub.docker.com/r/{repository}");
    let body = client
        .get(&url)
        .header(USER_AGENT, user_agent)
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| AppError::Http {
            url: url.clone(),
            reason: error.to_string(),
        })?
        .text()
        .map_err(|error| AppError::Http {
            url: url.clone(),
            reason: error.to_string(),
        })?;

    let digest = Regex::new(r"sha256:[a-f0-9]{64}")
        .ok()
        .and_then(|regex| regex.find(&body))
        .map(|match_| match_.as_str().to_string());

    let github_url = extract_github_url(&body);

    Ok((digest, github_url))
}

fn extract_github_url(text: &str) -> Option<String> {
    let regex = Regex::new(r"https://github.com/[A-Za-z0-9._/-]+").ok()?;
    regex.find(text).map(|match_| match_.as_str().to_string())
}

fn parse_image_reference(image: &str) -> Result<ParsedImageRef, AppError> {
    let cleaned = image
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .trim_matches('`')
        .to_string();

    if cleaned.is_empty() {
        return Err(AppError::InvalidInput {
            reason: "image reference cannot be empty".to_string(),
        });
    }

    if cleaned.chars().any(char::is_whitespace) {
        return Err(AppError::InvalidInput {
            reason: format!("image reference contains whitespace: {cleaned}"),
        });
    }

    let (name_part, digest) = if let Some((base, digest_value)) = cleaned.split_once('@') {
        (base, Some(digest_value.to_string()))
    } else {
        (cleaned.as_str(), None)
    };

    let mut registry = "docker.io".to_string();
    let mut repository = name_part.to_string();

    if let Some((first, rest)) = name_part.split_once('/') {
        if first.contains('.') || first.contains(':') || first.eq_ignore_ascii_case("localhost") {
            registry = first.to_ascii_lowercase();
            repository = rest.to_string();
        }
    }

    if registry == "docker.io" && !repository.contains('/') {
        repository = format!("library/{repository}");
    }

    if repository.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("image repository segment is empty: {cleaned}"),
        });
    }

    let (repo_only, tag_part) = split_tag(&repository);
    let repository = repo_only.to_string();
    let tag = tag_part.to_string();

    let reference = digest.unwrap_or_else(|| tag.clone());
    let normalized = if is_digest_reference(&reference) {
        format!("{registry}/{repository}@{reference}")
    } else {
        format!("{registry}/{repository}:{reference}")
    };

    Ok(ParsedImageRef {
        registry,
        repository,
        reference,
        normalized,
        tag,
    })
}

fn is_digest_reference(reference: &str) -> bool {
    reference
        .get(0..7)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("sha256:"))
}

fn split_tag(repository: &str) -> (&str, &str) {
    let last_slash = repository.rfind('/');
    let last_colon = repository.rfind(':');

    if let Some(colon_index) = last_colon {
        if match last_slash {
            Some(slash_index) => colon_index > slash_index,
            None => true,
        } {
            let (name, tag_with_colon) = repository.split_at(colon_index);
            return (name, &tag_with_colon[1..]);
        }
    }

    (repository, "latest")
}

fn extract_platform_from_config_payload(value: &Value) -> Option<Platform> {
    let os = value.get("os").and_then(Value::as_str)?;
    let arch = value.get("architecture").and_then(Value::as_str)?;
    Some(Platform {
        os: os.to_string(),
        arch: arch.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use crate::model::Platform;
    use serde_json::json;

    use super::{
        extract_platform_from_config_payload, infer_docs_url, is_digest_reference,
        parse_image_reference, validate_realm_url,
    };

    #[test]
    fn validate_realm_url_rejects_non_https() {
        let result = validate_realm_url("http://auth.docker.io/token", "docker.io");
        assert!(result.is_err());
    }

    #[test]
    fn validate_realm_url_rejects_outside_domain() {
        let result = validate_realm_url("https://evil.example/token", "docker.io");
        assert!(result.is_err());
    }

    #[test]
    fn validate_realm_url_accepts_subdomain() {
        let result = validate_realm_url("https://auth.docker.io/token", "docker.io");
        assert!(result.is_ok());
    }

    #[test]
    fn validate_realm_url_rejects_localhost_host() {
        let result = validate_realm_url("https://localhost/token", "localhost");
        assert!(result.is_err());
    }

    #[test]
    fn validate_realm_url_rejects_private_ipv4_host() {
        let result = validate_realm_url("https://10.0.0.7/token", "10.0.0.7");
        assert!(result.is_err());
    }

    #[test]
    fn infer_docs_url_returns_quay_repository_link() {
        let parsed =
            parse_image_reference("quay.io/org/service:1.0").expect("parse should succeed");
        let docs = infer_docs_url(&parsed);
        assert_eq!(
            docs.as_deref(),
            Some("https://quay.io/repository/org/service")
        );
    }

    #[test]
    fn infer_docs_url_returns_ghcr_github_link() {
        let parsed =
            parse_image_reference("ghcr.io/openfaas/gateway:latest").expect("parse should succeed");
        let docs = infer_docs_url(&parsed);
        assert_eq!(docs.as_deref(), Some("https://github.com/openfaas/gateway"));
    }

    #[test]
    fn extract_platform_from_config_payload_reads_os_and_architecture() {
        let payload = json!({
            "architecture": "amd64",
            "os": "linux"
        });
        let platform = extract_platform_from_config_payload(&payload);
        assert_eq!(
            platform,
            Some(Platform {
                os: "linux".to_string(),
                arch: "amd64".to_string(),
            })
        );
    }

    #[test]
    fn parse_image_reference_preserves_case_for_repository_and_tag() {
        let parsed =
            parse_image_reference("ghcr.io/OpenFaaS/Gateway:RC1").expect("parse should succeed");
        assert_eq!(parsed.registry, "ghcr.io");
        assert_eq!(parsed.repository, "OpenFaaS/Gateway");
        assert_eq!(parsed.reference, "RC1");
        assert_eq!(parsed.normalized, "ghcr.io/OpenFaaS/Gateway:RC1");
    }

    #[test]
    fn is_digest_reference_accepts_uppercase_prefix() {
        assert!(is_digest_reference("SHA256:abc"));
    }
}
