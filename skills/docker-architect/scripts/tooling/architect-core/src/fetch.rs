//! Metadata fetchers for API-first and fallback research.

use std::collections::BTreeSet;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::time::Duration;

use regex::Regex;
use reqwest::blocking::{Client, Response};
use reqwest::header::{ACCEPT, AUTHORIZATION, USER_AGENT, WWW_AUTHENTICATE};
use serde::Deserialize;
use serde_json::Value;
use url::Url;

use crate::error::AppError;
use crate::model::{ImageProfile, OciLabelProfile, Platform, RuntimeProfile, SourceRecord};

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
    tag_url: String,
    repo_url: String,
}

#[derive(Debug, Default)]
struct RegistryManifestDetails {
    digest: Option<String>,
    platforms: Vec<Platform>,
    config_digest: Option<String>,
    manifest_url: String,
}

#[derive(Debug, Default)]
struct ConfigBlobDetails {
    platform: Option<Platform>,
    runtime: RuntimeProfile,
    blob_url: String,
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
/// let profile = fetch_image_profile("nginx:1.27", true, "agent-skills-docker-architect-compose/0.1")?;
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
    let mut sources = Vec::new();

    let mut digest: Option<String> = if is_digest_reference(&parsed.reference) {
        Some(parsed.reference.clone())
    } else {
        None
    };
    let mut platforms: Vec<Platform> = Vec::new();
    let mut docs_url: Option<String> = None;
    let mut dockerfile_url: Option<String> = None;
    let mut runtime = RuntimeProfile::default();

    if parsed.registry == "docker.io" {
        match fetch_docker_hub_metadata(&client, &parsed, user_agent) {
            Ok(hub) => {
                if platforms.is_empty() {
                    platforms = hub.platforms;
                }
                docs_url = hub.docs_url;
                dockerfile_url = hub.dockerfile_url;
                sources.push(SourceRecord {
                    kind: "docker-hub-api".to_string(),
                    url: hub.tag_url,
                    status: "ok".to_string(),
                    digest: hub.digest,
                });
                sources.push(SourceRecord {
                    kind: "docker-hub-api".to_string(),
                    url: hub.repo_url,
                    status: "ok".to_string(),
                    digest: None,
                });
                notes.push("source:docker-hub-api".to_string());
            }
            Err(error) => {
                let tag_url = format!(
                    "https://hub.docker.com/v2/repositories/{}/tags/{}",
                    parsed.repository, parsed.tag
                );
                sources.push(SourceRecord {
                    kind: "docker-hub-api".to_string(),
                    url: tag_url,
                    status: format!("failed:{error}"),
                    digest: None,
                });
                notes.push(format!("docker-hub-api-failed:{error}"));
            }
        }
    }

    let mut registry_config_digest = None;
    let should_fetch_registry =
        parsed.registry == "docker.io" || digest.is_none() || platforms.is_empty();
    if should_fetch_registry {
        match fetch_registry_manifest(&client, &parsed, user_agent) {
            Ok(manifest) => {
                if parsed.registry == "docker.io" {
                    if manifest.digest.is_some() {
                        digest = manifest.digest.clone();
                    }
                } else if digest.is_none() {
                    digest = manifest.digest.clone();
                }

                if !manifest.platforms.is_empty() {
                    platforms = manifest.platforms;
                }
                registry_config_digest = manifest.config_digest;
                sources.push(SourceRecord {
                    kind: "registry-v2".to_string(),
                    url: manifest.manifest_url,
                    status: "ok".to_string(),
                    digest: manifest.digest,
                });
                notes.push("source:registry-v2".to_string());
            }
            Err(error) => {
                let manifest_url = format!(
                    "https://{}/v2/{}/manifests/{}",
                    registry_api_host(&parsed.registry),
                    parsed.repository,
                    parsed.reference
                );
                sources.push(SourceRecord {
                    kind: "registry-v2".to_string(),
                    url: manifest_url,
                    status: format!("failed:{error}"),
                    digest: None,
                });
                notes.push(format!("registry-v2-failed:{error}"));
            }
        }
    }

    if let Some(config_digest) = registry_config_digest {
        match fetch_config_blob_details(&client, &parsed, &config_digest, user_agent) {
            Ok(config) => {
                if platforms.is_empty() {
                    if let Some(platform) = config.platform {
                        platforms.push(platform);
                    }
                }
                if runtime_profile_has_data(&config.runtime) {
                    runtime = config.runtime;
                }
                sources.push(SourceRecord {
                    kind: "registry-v2-config".to_string(),
                    url: config.blob_url,
                    status: "ok".to_string(),
                    digest: Some(config_digest),
                });
            }
            Err(error) => {
                let blob_url = format!(
                    "https://{}/v2/{}/blobs/{}",
                    registry_api_host(&parsed.registry),
                    parsed.repository,
                    config_digest
                );
                sources.push(SourceRecord {
                    kind: "registry-v2-config".to_string(),
                    url: blob_url,
                    status: format!("failed:{error}"),
                    digest: Some(config_digest),
                });
                notes.push(format!("registry-v2-config-failed:{error}"));
            }
        }
    }

    if allow_scrape_fallback
        && parsed.registry == "docker.io"
        && (digest.is_none() || dockerfile_url.is_none())
    {
        let scrape_url = format!("https://hub.docker.com/r/{}", parsed.repository);
        match scrape_hub_page(&client, &parsed.repository, user_agent) {
            Ok((scraped_digest, scraped_repo_url)) => {
                if digest.is_none() {
                    digest = scraped_digest.clone();
                }
                if dockerfile_url.is_none() {
                    dockerfile_url = scraped_repo_url;
                }
                sources.push(SourceRecord {
                    kind: "html-fallback".to_string(),
                    url: scrape_url,
                    status: "ok".to_string(),
                    digest: scraped_digest,
                });
                notes.push("source:html-fallback".to_string());
            }
            Err(error) => {
                sources.push(SourceRecord {
                    kind: "html-fallback".to_string(),
                    url: scrape_url,
                    status: format!("failed:{error}"),
                    digest: None,
                });
                notes.push(format!("html-fallback-failed:{error}"));
            }
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
        runtime,
        sources,
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
/// let profiles = fetch_profiles(&["nginx:1.27".to_string()], true, "agent-skills-docker-architect-compose/0.1")?;
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

/// Normalize an image reference into a fully-qualified deterministic form.
///
/// # Arguments
/// * `image` - Raw image reference.
///
/// # Returns
/// * `Ok(String)` with normalized reference, such as `docker.io/library/nginx:1.27`.
/// * `Err(AppError)` when the image reference cannot be parsed.
pub fn normalize_image_reference(image: &str) -> Result<String, AppError> {
    parse_image_reference(image).map(|parsed| parsed.normalized)
}

fn fetch_docker_hub_metadata(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
) -> Result<DockerHubMetadata, AppError> {
    let tag_url = format!(
        "https://hub.docker.com/v2/repositories/{}/tags/{}",
        parsed.repository, parsed.tag
    );
    let repo_url = format!(
        "https://hub.docker.com/v2/repositories/{}",
        parsed.repository
    );

    let (digest, platforms) = if is_digest_reference(&parsed.reference) {
        (None, Vec::new())
    } else {
        fetch_docker_hub_tag_metadata(client, &tag_url, user_agent)?
    };
    let dockerfile_url = fetch_docker_hub_repo_dockerfile_url(client, &repo_url, user_agent)?;

    Ok(DockerHubMetadata {
        digest,
        platforms,
        docs_url: Some(format!("https://hub.docker.com/r/{}", parsed.repository)),
        dockerfile_url,
        tag_url,
        repo_url,
    })
}

fn fetch_docker_hub_tag_metadata(
    client: &Client,
    tag_url: &str,
    user_agent: &str,
) -> Result<(Option<String>, Vec<Platform>), AppError> {
    let tag_response = client
        .get(tag_url)
        .header(USER_AGENT, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: tag_url.to_string(),
            reason: error.to_string(),
        })?;

    if !tag_response.status().is_success() {
        return Err(AppError::Http {
            url: tag_url.to_string(),
            reason: format!("unexpected status {}", tag_response.status()),
        });
    }

    let tag_payload: DockerHubTagResponse =
        tag_response.json().map_err(|error| AppError::Http {
            url: tag_url.to_string(),
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

    Ok((digest, dedup_platforms(platforms)))
}

fn fetch_docker_hub_repo_dockerfile_url(
    client: &Client,
    repo_url: &str,
    user_agent: &str,
) -> Result<Option<String>, AppError> {
    let repo_response = client
        .get(repo_url)
        .header(USER_AGENT, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: repo_url.to_string(),
            reason: error.to_string(),
        })?;

    if !repo_response.status().is_success() {
        return Ok(None);
    }

    let repo_payload: DockerHubRepoResponse =
        repo_response.json().map_err(|error| AppError::Http {
            url: repo_url.to_string(),
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
) -> Result<RegistryManifestDetails, AppError> {
    let registry_host = registry_api_host(&parsed.registry);
    let manifest_url = format!(
        "https://{registry_host}/v2/{}/manifests/{}",
        parsed.repository, parsed.reference
    );

    let response = request_registry_with_auth(
        client,
        &manifest_url,
        &parsed.repository,
        &registry_host,
        user_agent,
    )?;
    parse_manifest_response(client, parsed, user_agent, &manifest_url, response)
}

fn parse_manifest_response(
    client: &Client,
    parsed: &ParsedImageRef,
    user_agent: &str,
    url: &str,
    response: Response,
) -> Result<RegistryManifestDetails, AppError> {
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
    let mut config_digest = None;
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

        if let Some(chosen_manifest_digest) = choose_manifest_digest_for_config(manifests) {
            config_digest =
                fetch_manifest_config_digest(client, parsed, &chosen_manifest_digest, user_agent)?;
        }
    } else if let Some(digest_value) = value
        .get("config")
        .and_then(|config| config.get("digest"))
        .and_then(Value::as_str)
    {
        config_digest = Some(digest_value.to_string());
    }

    Ok(RegistryManifestDetails {
        digest,
        platforms: dedup_platforms(platforms),
        config_digest,
        manifest_url: url.to_string(),
    })
}

fn choose_manifest_digest_for_config(manifests: &[Value]) -> Option<String> {
    for manifest in manifests {
        let os = manifest
            .get("platform")
            .and_then(|platform| platform.get("os"))
            .and_then(Value::as_str);
        let arch = manifest
            .get("platform")
            .and_then(|platform| platform.get("architecture"))
            .and_then(Value::as_str);
        if matches!(os, Some("linux")) && matches!(arch, Some("amd64")) {
            if let Some(digest) = manifest.get("digest").and_then(Value::as_str) {
                return Some(digest.to_string());
            }
        }
    }

    manifests
        .first()
        .and_then(|manifest| manifest.get("digest").and_then(Value::as_str))
        .map(ToOwned::to_owned)
}

fn fetch_manifest_config_digest(
    client: &Client,
    parsed: &ParsedImageRef,
    manifest_digest: &str,
    user_agent: &str,
) -> Result<Option<String>, AppError> {
    let registry_host = registry_api_host(&parsed.registry);
    let manifest_url = format!(
        "https://{registry_host}/v2/{}/manifests/{manifest_digest}",
        parsed.repository
    );
    let response = request_registry_with_auth(
        client,
        &manifest_url,
        &parsed.repository,
        &registry_host,
        user_agent,
    )?;
    if !response.status().is_success() {
        return Ok(None);
    }

    let value: Value = response.json().map_err(|error| AppError::Http {
        url: manifest_url,
        reason: format!("manifest payload parse failed: {error}"),
    })?;
    Ok(value
        .get("config")
        .and_then(|config| config.get("digest"))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned))
}

fn fetch_config_blob_details(
    client: &Client,
    parsed: &ParsedImageRef,
    config_digest: &str,
    user_agent: &str,
) -> Result<ConfigBlobDetails, AppError> {
    let registry_host = registry_api_host(&parsed.registry);
    let blob_url = format!(
        "https://{registry_host}/v2/{}/blobs/{config_digest}",
        parsed.repository
    );
    let response = request_registry_with_auth(
        client,
        &blob_url,
        &parsed.repository,
        &registry_host,
        user_agent,
    )?;
    if !response.status().is_success() {
        return Err(AppError::Http {
            url: blob_url,
            reason: format!("unexpected status {}", response.status()),
        });
    }

    let value: Value = response.json().map_err(|error| AppError::Http {
        url: blob_url.clone(),
        reason: format!("config blob parse failed: {error}"),
    })?;

    Ok(ConfigBlobDetails {
        platform: extract_platform_from_config_payload(&value),
        runtime: extract_runtime_profile_from_config_payload(&value),
        blob_url,
    })
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
    url: &str,
    repository: &str,
    registry_host: &str,
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

    let token = fetch_bearer_token(client, &auth, repository, registry_host, user_agent)?;
    request_registry(client, url, Some(&token), user_agent)
}

fn fetch_bearer_token(
    client: &Client,
    challenge: &AuthChallenge,
    repository: &str,
    registry_host: &str,
    user_agent: &str,
) -> Result<String, AppError> {
    let mut token_url = validate_realm_url(&challenge.realm, registry_host)?;

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

fn validate_realm_url(realm: &str, registry_host: &str) -> Result<Url, AppError> {
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

    let normalized_registry_host = Url::parse(&format!("https://{registry_host}"))
        .map_err(|error| AppError::Http {
            url: registry_host.to_string(),
            reason: format!("invalid registry host: {error}"),
        })?
        .host_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| AppError::Http {
            url: registry_host.to_string(),
            reason: "registry host resolution failed".to_string(),
        })?;

    if !is_allowed_realm_host(realm_host, &normalized_registry_host) {
        return Err(AppError::Http {
            url: realm.to_string(),
            reason: format!(
                "token realm host {realm_host} is not in registry domain {normalized_registry_host}"
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

fn is_allowed_realm_host(realm_host: &str, registry_host: &str) -> bool {
    if is_same_or_subdomain(realm_host, registry_host) {
        return true;
    }

    // Docker Hub uses registry-1.docker.io and auth.docker.io.
    is_docker_io_host(realm_host) && is_docker_io_host(registry_host)
}

fn is_docker_io_host(host: &str) -> bool {
    let host = host.to_ascii_lowercase();
    host == "docker.io" || host.ends_with(".docker.io")
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

    let digest_regex =
        Regex::new(r"sha256:[a-f0-9]{64}").map_err(|error| AppError::InvalidInput {
            reason: format!("failed to compile digest regex: {error}"),
        })?;
    let digest = digest_regex
        .find(&body)
        .map(|match_| match_.as_str().to_string());

    let github_url = extract_github_url(&body);

    Ok((digest, github_url))
}

fn extract_github_url(text: &str) -> Option<String> {
    let regex = match Regex::new(r"https://github.com/[A-Za-z0-9._/-]+") {
        Ok(value) => value,
        Err(_) => return None,
    };
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

fn registry_api_host(registry: &str) -> String {
    if registry == "docker.io" {
        return "registry-1.docker.io".to_string();
    }
    registry.to_string()
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

fn extract_runtime_profile_from_config_payload(value: &Value) -> RuntimeProfile {
    let mut profile = RuntimeProfile::default();

    let config = value.get("config").unwrap_or(value);
    profile.user = config
        .get("User")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .filter(|user| !user.is_empty());
    profile.entrypoint = parse_command_list(config.get("Entrypoint"));
    profile.cmd = parse_command_list(config.get("Cmd"));
    profile.working_dir = config
        .get("WorkingDir")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .filter(|dir| !dir.is_empty());
    profile.env_keys = parse_env_keys(config.get("Env"));
    profile.oci = parse_oci_labels(config.get("Labels"));

    profile
}

fn parse_command_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .map(ToOwned::to_owned)
            .collect(),
        Some(Value::String(text)) => vec![text.to_string()],
        _ => Vec::new(),
    }
}

fn parse_env_keys(value: Option<&Value>) -> Vec<String> {
    let mut keys = BTreeSet::new();
    if let Some(Value::Array(items)) = value {
        for entry in items {
            if let Some(value) = entry.as_str() {
                if let Some((name, _)) = value.split_once('=') {
                    if !name.is_empty() {
                        keys.insert(name.to_string());
                    }
                }
            }
        }
    }
    keys.into_iter().collect()
}

fn parse_oci_labels(value: Option<&Value>) -> OciLabelProfile {
    let mut labels = OciLabelProfile::default();
    if let Some(Value::Object(map)) = value {
        labels.source = map
            .get("org.opencontainers.image.source")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);
        labels.revision = map
            .get("org.opencontainers.image.revision")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);
        labels.licenses = map
            .get("org.opencontainers.image.licenses")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);
    }
    labels
}

fn runtime_profile_has_data(profile: &RuntimeProfile) -> bool {
    profile.user.is_some()
        || !profile.entrypoint.is_empty()
        || !profile.cmd.is_empty()
        || profile.working_dir.is_some()
        || !profile.env_keys.is_empty()
        || profile.oci.source.is_some()
        || profile.oci.revision.is_some()
        || profile.oci.licenses.is_some()
}

fn dedup_platforms(platforms: Vec<Platform>) -> Vec<Platform> {
    let mut set = BTreeSet::new();
    for platform in platforms {
        set.insert((platform.os, platform.arch));
    }
    set.into_iter()
        .map(|(os, arch)| Platform { os, arch })
        .collect()
}

#[cfg(test)]
mod tests {
    use crate::model::{OciLabelProfile, Platform, RuntimeProfile};
    use serde_json::json;

    use super::{
        extract_platform_from_config_payload, extract_runtime_profile_from_config_payload,
        infer_docs_url, is_digest_reference, normalize_image_reference, parse_image_reference,
        registry_api_host, validate_realm_url,
    };

    #[test]
    fn validate_realm_url_rejects_non_https() {
        let result = validate_realm_url("http://auth.docker.io/token", "registry-1.docker.io");
        assert!(result.is_err());
    }

    #[test]
    fn validate_realm_url_rejects_outside_domain() {
        let result = validate_realm_url("https://evil.example/token", "registry-1.docker.io");
        assert!(result.is_err());
    }

    #[test]
    fn validate_realm_url_accepts_docker_hub_auth_host() {
        let result = validate_realm_url("https://auth.docker.io/token", "registry-1.docker.io");
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
    fn extract_runtime_profile_reads_selected_fields() {
        let payload = json!({
            "config": {
                "User": "1000:1000",
                "Entrypoint": ["/entrypoint.sh"],
                "Cmd": ["serve", "--port", "8080"],
                "WorkingDir": "/work",
                "Env": ["A=1", "B=2"],
                "Labels": {
                    "org.opencontainers.image.source": "https://github.com/example/repo",
                    "org.opencontainers.image.revision": "abc123",
                    "org.opencontainers.image.licenses": "MIT"
                }
            }
        });

        let runtime = extract_runtime_profile_from_config_payload(&payload);
        assert_eq!(
            runtime,
            RuntimeProfile {
                user: Some("1000:1000".to_string()),
                entrypoint: vec!["/entrypoint.sh".to_string()],
                cmd: vec![
                    "serve".to_string(),
                    "--port".to_string(),
                    "8080".to_string()
                ],
                working_dir: Some("/work".to_string()),
                env_keys: vec!["A".to_string(), "B".to_string()],
                oci: OciLabelProfile {
                    source: Some("https://github.com/example/repo".to_string()),
                    revision: Some("abc123".to_string()),
                    licenses: Some("MIT".to_string()),
                },
            }
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

    #[test]
    fn registry_api_host_maps_docker_hub_registry() {
        assert_eq!(registry_api_host("docker.io"), "registry-1.docker.io");
        assert_eq!(registry_api_host("ghcr.io"), "ghcr.io");
    }

    #[test]
    fn normalize_image_reference_expands_default_registry_and_namespace() {
        let normalized =
            normalize_image_reference("nginx:1.27").expect("normalization should succeed");
        assert_eq!(normalized, "docker.io/library/nginx:1.27");
    }
}
