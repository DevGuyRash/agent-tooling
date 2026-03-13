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
use crate::knowledge;
use crate::model::{
    EnvVar, HealthcheckProfile, ImageProfile, OciLabelProfile, Platform, RecommendedEnvVar,
    ResearchedConfig, RuntimeProfile, RuntimeSignatures, SourceRecord,
};

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
    source_repo_url: Option<String>,
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
    let client = build_http_client()?;
    fetch_image_profile_with_client(&client, image, allow_scrape_fallback, user_agent)
}

fn fetch_image_profile_with_client(
    client: &Client,
    image: &str,
    allow_scrape_fallback: bool,
    user_agent: &str,
) -> Result<ImageProfile, AppError> {
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
    let mut source_repo_url: Option<String> = None;
    let mut runtime = RuntimeProfile::default();
    let mut config_digest_for_profile: Option<String> = None;

    if parsed.registry == "docker.io" {
        match fetch_docker_hub_metadata(client, &parsed, user_agent) {
            Ok(hub) => {
                if platforms.is_empty() {
                    platforms = hub.platforms;
                }
                docs_url = hub.docs_url;
                dockerfile_url = hub.dockerfile_url;
                source_repo_url = hub.source_repo_url;
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
                let status = stable_failure_status(&error);
                sources.push(SourceRecord {
                    kind: "docker-hub-api".to_string(),
                    url: tag_url,
                    status: status.clone(),
                    digest: None,
                });
                notes.push(format!("docker-hub-api-failed:{status}"));
            }
        }
    }

    let mut registry_config_digest = None;
    let should_fetch_registry =
        parsed.registry == "docker.io" || digest.is_none() || platforms.is_empty();
    if should_fetch_registry {
        match fetch_registry_manifest(client, &parsed, user_agent) {
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
                config_digest_for_profile = registry_config_digest.clone();
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
                let status = stable_failure_status(&error);
                sources.push(SourceRecord {
                    kind: "registry-v2".to_string(),
                    url: manifest_url,
                    status: status.clone(),
                    digest: None,
                });
                notes.push(format!("registry-v2-failed:{status}"));
            }
        }
    }

    if let Some(config_digest) = registry_config_digest {
        match fetch_config_blob_details(&parsed, &config_digest, user_agent) {
            Ok(config) => {
                if platforms.is_empty() {
                    if let Some(platform) = config.platform {
                        platforms.push(platform);
                    }
                }
                if runtime_profile_has_data(&config.runtime) {
                    runtime = config.runtime;
                }
                if let Some(source) = runtime.oci.source.clone() {
                    if source_repo_url.is_none() {
                        source_repo_url = Some(source);
                    }
                    notes.push("source:oci-label".to_string());
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
                let status = stable_failure_status(&error);
                sources.push(SourceRecord {
                    kind: "registry-v2-config".to_string(),
                    url: blob_url,
                    status: status.clone(),
                    digest: Some(config_digest),
                });
                notes.push(format!("registry-v2-config-failed:{status}"));
            }
        }
    }
    if allow_scrape_fallback
        && parsed.registry == "docker.io"
        && (digest.is_none() || source_repo_url.is_none())
    {
        let scrape_url = format!("https://hub.docker.com/r/{}", parsed.repository);
        match scrape_hub_page(client, &parsed.repository, user_agent) {
            Ok((scraped_digest, scraped_repo_url)) => {
                if digest.is_none() {
                    digest = scraped_digest.clone();
                }
                if source_repo_url.is_none() {
                    source_repo_url = scraped_repo_url;
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
                let status = stable_failure_status(&error);
                sources.push(SourceRecord {
                    kind: "html-fallback".to_string(),
                    url: scrape_url,
                    status: status.clone(),
                    digest: None,
                });
                notes.push(format!("html-fallback-failed:{status}"));
            }
        }
    }

    if docs_url.is_none() {
        docs_url = infer_docs_url(&parsed);
        if docs_url.is_some() {
            notes.push("source:docs-heuristic".to_string());
        }
    }

    runtime.signatures = detect_runtime_signatures(&runtime);
    let mut researched_config =
        knowledge::researched_config_for_image(&parsed.normalized, &runtime.signatures)?
            .unwrap_or_default();
    if allow_scrape_fallback {
        enrich_researched_env_from_docs(
            client,
            user_agent,
            docs_url.as_deref(),
            source_repo_url.as_deref().or(dockerfile_url.as_deref()),
            &mut researched_config,
            &mut sources,
            &mut notes,
        );
    }

    Ok(ImageProfile {
        id: String::new(),
        image: parsed.normalized,
        docs_url,
        dockerfile_url,
        source_repo_url,
        digest,
        config_digest: config_digest_for_profile,
        platforms,
        runtime,
        sources,
        notes,
        researched_config,
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
    let client = build_http_client()?;
    let mut output = Vec::with_capacity(images.len());
    for image in images {
        output.push(fetch_image_profile_with_client(
            &client,
            image,
            allow_scrape_fallback,
            user_agent,
        )?);
    }
    Ok(output)
}

fn build_http_client() -> Result<Client, AppError> {
    Client::builder()
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|error| AppError::InvalidInput {
            reason: format!("failed to build http client: {error}"),
        })
}

fn build_blob_http_client() -> Result<Client, AppError> {
    Client::builder()
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::limited(5))
        .build()
        .map_err(|error| AppError::InvalidInput {
            reason: format!("failed to build blob http client: {error}"),
        })
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
    let source_repo_url =
        fetch_docker_hub_repo_dockerfile_url(client, &repo_url, &parsed.repository, user_agent)?;

    Ok(DockerHubMetadata {
        digest,
        platforms,
        docs_url: Some(format!("https://hub.docker.com/r/{}", parsed.repository)),
        dockerfile_url: None,
        source_repo_url,
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
    image_repository: &str,
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
        .and_then(|description| extract_github_url(description, image_repository)))
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
    parsed: &ParsedImageRef,
    config_digest: &str,
    user_agent: &str,
) -> Result<ConfigBlobDetails, AppError> {
    let blob_client = build_blob_http_client()?;
    let registry_host = registry_api_host(&parsed.registry);
    let blob_url = format!(
        "https://{registry_host}/v2/{}/blobs/{config_digest}",
        parsed.repository
    );
    let response = request_registry_with_auth(
        &blob_client,
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
        match key.to_ascii_lowercase().as_str() {
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

    let github_url = extract_github_url(&body, repository);

    Ok((digest, github_url))
}

fn extract_github_url(text: &str, image_repository: &str) -> Option<String> {
    let regex = match Regex::new(r"https://github.com/[A-Za-z0-9._/-]+") {
        Ok(value) => value,
        Err(_) => return None,
    };
    let matched = regex
        .find_iter(text)
        .map(|match_| match_.as_str())
        .find(|candidate| github_url_matches_image_repository(candidate, image_repository))
        .map(ToOwned::to_owned);
    matched
}

fn github_url_matches_image_repository(url: &str, image_repository: &str) -> bool {
    let Some((owner, repository)) = parse_github_owner_repo(url) else {
        return false;
    };

    let image_tokens = image_repository_tokens(image_repository);
    let github_tokens = image_repository_tokens(&format!("{owner}/{repository}"));
    !image_tokens.is_disjoint(&github_tokens)
}

fn image_repository_tokens(value: &str) -> BTreeSet<String> {
    value
        .split('/')
        .flat_map(|segment| segment.split(['-', '_', '.']))
        .map(|segment| segment.trim().to_ascii_lowercase())
        .filter(|segment| !segment.is_empty() && segment != "library")
        .collect()
}

fn enrich_researched_env_from_docs(
    client: &Client,
    user_agent: &str,
    docs_url: Option<&str>,
    dockerfile_url: Option<&str>,
    researched_config: &mut ResearchedConfig,
    sources: &mut Vec<SourceRecord>,
    notes: &mut Vec<String>,
) {
    let candidates = docs_scan_candidates(docs_url, dockerfile_url);
    if candidates.is_empty() {
        return;
    }

    let mut reported_failure = false;
    for url in candidates {
        match fetch_docs_text(client, &url, user_agent) {
            Ok(body) => {
                sources.push(SourceRecord {
                    kind: "docs-env-scan".to_string(),
                    url: url.clone(),
                    status: "ok".to_string(),
                    digest: None,
                });
                let discovered = extract_recommended_env_from_docs(&body);
                if discovered.is_empty() {
                    continue;
                }

                let mut existing_keys: BTreeSet<String> = researched_config
                    .recommended_env
                    .iter()
                    .map(|item| item.key.to_ascii_uppercase())
                    .collect();
                let mut added = 0usize;
                for key in discovered {
                    if !existing_keys.insert(key.to_ascii_uppercase()) {
                        continue;
                    }
                    researched_config.recommended_env.push(RecommendedEnvVar {
                        key,
                        default_value: None,
                        required: false,
                        rationale: Some(
                            "discovered from upstream documentation environment section"
                                .to_string(),
                        ),
                    });
                    added += 1;
                }
                researched_config
                    .recommended_env
                    .sort_by(|left, right| left.key.cmp(&right.key));
                if added > 0 {
                    notes.push(format!("source:docs-env-scan:{added}-added"));
                }
                return;
            }
            Err(error) => {
                let status = stable_failure_status(&error);
                sources.push(SourceRecord {
                    kind: "docs-env-scan".to_string(),
                    url: url.clone(),
                    status: status.clone(),
                    digest: None,
                });
                if !reported_failure {
                    notes.push(format!("docs-env-scan-failed:{status}"));
                    reported_failure = true;
                }
            }
        }
    }
}

fn docs_scan_candidates(docs_url: Option<&str>, dockerfile_url: Option<&str>) -> Vec<String> {
    let mut urls = BTreeSet::new();

    for candidate in [docs_url, dockerfile_url].into_iter().flatten() {
        if let Some((owner, repo)) = parse_github_owner_repo(candidate) {
            urls.insert(format!(
                "https://api.github.com/repos/{owner}/{repo}/readme"
            ));
            continue;
        }
        if candidate.ends_with(".md")
            || candidate.ends_with(".txt")
            || candidate.contains("raw.githubusercontent.com")
        {
            urls.insert(candidate.to_string());
        }
    }

    urls.into_iter().collect()
}

fn parse_github_owner_repo(url: &str) -> Option<(String, String)> {
    let parsed = Url::parse(url).ok()?;
    if parsed.host_str()? != "github.com" {
        return None;
    }
    let mut segments = parsed
        .path_segments()?
        .filter(|segment| !segment.is_empty());
    let owner = segments.next()?.to_string();
    let repository = segments.next()?.trim_end_matches(".git").to_string();
    if owner.is_empty() || repository.is_empty() {
        return None;
    }
    Some((owner, repository))
}

fn fetch_docs_text(client: &Client, url: &str, user_agent: &str) -> Result<String, AppError> {
    let response = build_docs_request(client, url, user_agent)
        .send()
        .map_err(|error| AppError::Http {
            url: url.to_string(),
            reason: error.to_string(),
        })?;
    if !response.status().is_success() {
        return Err(AppError::Http {
            url: url.to_string(),
            reason: format!("unexpected status {}", response.status()),
        });
    }
    response.text().map_err(|error| AppError::Http {
        url: url.to_string(),
        reason: error.to_string(),
    })
}

fn build_docs_request(
    client: &Client,
    url: &str,
    user_agent: &str,
) -> reqwest::blocking::RequestBuilder {
    let mut request = client.get(url).header(USER_AGENT, user_agent);
    if url.starts_with("https://api.github.com/repos/") {
        request = request
            .header(ACCEPT, "application/vnd.github.v3.raw")
            .header("X-GitHub-Api-Version", "2022-11-28");
    }
    request
}

fn extract_recommended_env_from_docs(content: &str) -> Vec<String> {
    let env_key_re = match Regex::new(r"\b[A-Z][A-Z0-9_]{2,}\b") {
        Ok(value) => value,
        Err(_) => return Vec::new(),
    };

    let mut discovered = BTreeSet::new();
    for line in content.lines() {
        let lower = line.to_ascii_lowercase();
        let context_match = lower.contains("environment")
            || lower.contains("env var")
            || lower.contains("variable")
            || line.contains('|');
        if !context_match {
            continue;
        }
        for match_ in env_key_re.find_iter(line) {
            let candidate = match_.as_str();
            if is_probable_env_key(candidate) {
                discovered.insert(candidate.to_string());
            }
        }
    }
    discovered.into_iter().collect()
}

fn is_probable_env_key(value: &str) -> bool {
    if value.ends_with("_FILE") {
        return false;
    }
    if value.contains('_') {
        return true;
    }
    value.ends_with("TOKEN")
        || value.ends_with("PASSWORD")
        || value.ends_with("SECRET")
        || value.ends_with("KEY")
        || value.ends_with("PORT")
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
    validate_image_reference_chars(&cleaned)?;

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
    validate_registry_host(&registry)?;

    if registry == "docker.io" && !repository.contains('/') {
        repository = format!("library/{repository}");
    }

    if repository.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("image repository segment is empty: {cleaned}"),
        });
    }

    let (repo_only, tag_part) = split_tag(&repository);
    let repository = if registry == "docker.io" {
        repo_only.to_ascii_lowercase()
    } else {
        repo_only.to_string()
    };
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

fn validate_image_reference_chars(cleaned: &str) -> Result<(), AppError> {
    let valid_chars = cleaned
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-' | '/' | ':' | '@'));
    if !valid_chars {
        return Err(AppError::InvalidInput {
            reason: format!("image reference contains unsupported characters: {cleaned}"),
        });
    }
    Ok(())
}

fn validate_registry_host(registry: &str) -> Result<(), AppError> {
    let host = Url::parse(&format!("https://{registry}"))
        .map_err(|error| AppError::InvalidInput {
            reason: format!("invalid registry host `{registry}`: {error}"),
        })?
        .host_str()
        .map(ToOwned::to_owned)
        .ok_or_else(|| AppError::InvalidInput {
            reason: format!("invalid registry host `{registry}`"),
        })?;

    if is_disallowed_host(&host) {
        return Err(AppError::InvalidInput {
            reason: format!("registry host `{host}` is not allowed"),
        });
    }

    Ok(())
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
    profile.env = parse_env_vars(config.get("Env"));
    profile.exposed_ports = parse_string_key_map(config.get("ExposedPorts"));
    profile.volumes = parse_string_key_map(config.get("Volumes"));
    profile.stop_signal = config
        .get("StopSignal")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .filter(|signal| !signal.is_empty());
    profile.healthcheck = parse_healthcheck(config.get("Healthcheck"));
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

fn parse_env_vars(value: Option<&Value>) -> Vec<EnvVar> {
    let mut vars = Vec::new();
    if let Some(Value::Array(items)) = value {
        for entry in items {
            let Some(raw) = entry.as_str() else {
                continue;
            };
            if raw.is_empty() {
                continue;
            }
            let (key, value) = match raw.split_once('=') {
                Some((key, value)) => (key.trim(), Some(value.to_string())),
                None => (raw.trim(), None),
            };
            if key.is_empty() {
                continue;
            }
            vars.push(EnvVar {
                key: key.to_string(),
                value,
            });
        }
    }
    vars.sort_by(|left, right| left.key.cmp(&right.key).then(left.value.cmp(&right.value)));
    vars.dedup();
    vars
}

fn parse_string_key_map(value: Option<&Value>) -> Vec<String> {
    let mut values = BTreeSet::new();
    if let Some(Value::Object(map)) = value {
        for key in map.keys() {
            if !key.is_empty() {
                values.insert(key.to_string());
            }
        }
    }
    values.into_iter().collect()
}

fn parse_healthcheck(value: Option<&Value>) -> Option<HealthcheckProfile> {
    let Some(Value::Object(map)) = value else {
        return None;
    };

    let test = parse_command_list(map.get("Test"));
    let interval_ns = map.get("Interval").and_then(Value::as_u64);
    let timeout_ns = map.get("Timeout").and_then(Value::as_u64);
    let start_period_ns = map.get("StartPeriod").and_then(Value::as_u64);
    let retries = map
        .get("Retries")
        .and_then(Value::as_u64)
        .and_then(|value| u32::try_from(value).ok());

    if test.is_empty()
        && interval_ns.is_none()
        && timeout_ns.is_none()
        && start_period_ns.is_none()
        && retries.is_none()
    {
        return None;
    }

    Some(HealthcheckProfile {
        test,
        interval_ns,
        timeout_ns,
        start_period_ns,
        retries,
    })
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

fn detect_runtime_signatures(profile: &RuntimeProfile) -> RuntimeSignatures {
    let mut signatures = RuntimeSignatures::default();

    for key in &profile.env_keys {
        let normalized = key.to_ascii_uppercase();
        if normalized.starts_with("NVIDIA_") {
            signatures.nvidia = true;
            signatures.gpu_compute = true;
        }
        if normalized.starts_with("ROCM_") || normalized.starts_with("HIP_") {
            signatures.rocm = true;
            signatures.gpu_compute = true;
        }
        if normalized.contains("OPENCL") || normalized.contains("OCL_ICD") {
            signatures.opencl = true;
            signatures.gpu_compute = true;
        }
    }

    for entry in &profile.env {
        let normalized = entry.key.to_ascii_uppercase();
        if normalized.starts_with("NVIDIA_") {
            signatures.nvidia = true;
            signatures.gpu_compute = true;
        }
        if normalized.starts_with("ROCM_") || normalized.starts_with("HIP_") {
            signatures.rocm = true;
            signatures.gpu_compute = true;
        }
        if normalized.contains("OPENCL") || normalized.contains("OCL_ICD") {
            signatures.opencl = true;
            signatures.gpu_compute = true;
        }
    }

    if profile
        .oci
        .source
        .as_deref()
        .map(|value| value.to_ascii_lowercase().contains("nvidia"))
        .unwrap_or(false)
    {
        signatures.nvidia = true;
        signatures.gpu_compute = true;
    }

    signatures
}

fn stable_failure_status(error: &AppError) -> String {
    match error {
        AppError::Http { reason, .. } => {
            if let Some(code) = parse_http_status(reason) {
                return format!("failed:http_status:{code}");
            }
            let reason_lower = reason.to_ascii_lowercase();
            if reason_lower.contains("timed out") || reason_lower.contains("timeout") {
                return "failed:timeout".to_string();
            }
            if reason_lower.contains("dns") || reason_lower.contains("name or service not known") {
                return "failed:dns".to_string();
            }
            if reason_lower.contains("tls") || reason_lower.contains("certificate") {
                return "failed:tls".to_string();
            }
            if reason_lower.contains("parse") {
                return "failed:parse".to_string();
            }
            "failed:http".to_string()
        }
        AppError::Serialization { .. } => "failed:parse".to_string(),
        AppError::InvalidInput { .. } => "failed:invalid-input".to_string(),
        AppError::Io { .. } => "failed:io".to_string(),
    }
}

fn parse_http_status(reason: &str) -> Option<u16> {
    let marker = "unexpected status ";
    let index = reason.find(marker)?;
    let status_text = reason[index + marker.len()..].split_whitespace().next()?;
    status_text.parse::<u16>().ok()
}

fn runtime_profile_has_data(profile: &RuntimeProfile) -> bool {
    profile.user.is_some()
        || !profile.entrypoint.is_empty()
        || !profile.cmd.is_empty()
        || profile.working_dir.is_some()
        || !profile.env_keys.is_empty()
        || !profile.env.is_empty()
        || !profile.exposed_ports.is_empty()
        || !profile.volumes.is_empty()
        || profile.stop_signal.is_some()
        || profile.healthcheck.is_some()
        || !profile.tools.is_empty()
        || !profile.tool_details.is_empty()
        || profile.signatures.gpu_compute
        || profile.signatures.opencl
        || profile.signatures.nvidia
        || profile.signatures.rocm
        || profile.signatures.distroless
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
    use crate::model::{
        EnvVar, HealthcheckProfile, OciLabelProfile, Platform, RuntimeProfile, RuntimeSignatures,
    };
    use reqwest::blocking::Client;
    use serde_json::json;

    use super::{
        build_docs_request, docs_scan_candidates, extract_github_url,
        extract_platform_from_config_payload, extract_recommended_env_from_docs,
        extract_runtime_profile_from_config_payload, infer_docs_url, is_digest_reference,
        normalize_image_reference, parse_auth_challenge, parse_github_owner_repo,
        parse_image_reference, registry_api_host, validate_realm_url,
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
    fn parse_auth_challenge_accepts_case_insensitive_parameter_keys() {
        let parsed = parse_auth_challenge(
            r#"Bearer Realm="https://auth.docker.io/token",Service="registry.docker.io",Scope="repo:library/nginx:pull""#,
        )
        .expect("challenge should parse");
        assert_eq!(parsed.realm, "https://auth.docker.io/token");
        assert_eq!(parsed.service.as_deref(), Some("registry.docker.io"));
        assert_eq!(parsed.scope.as_deref(), Some("repo:library/nginx:pull"));
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
                "ExposedPorts": {"8080/tcp": {}},
                "Volumes": {"/data": {}},
                "StopSignal": "SIGTERM",
                "Healthcheck": {
                    "Test": ["CMD", "/entrypoint.sh", "healthcheck"],
                    "Interval": 10000000000u64,
                    "Timeout": 3000000000u64,
                    "StartPeriod": 5000000000u64,
                    "Retries": 5
                },
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
                env: vec![
                    EnvVar {
                        key: "A".to_string(),
                        value: Some("1".to_string()),
                    },
                    EnvVar {
                        key: "B".to_string(),
                        value: Some("2".to_string()),
                    }
                ],
                exposed_ports: vec!["8080/tcp".to_string()],
                volumes: vec!["/data".to_string()],
                stop_signal: Some("SIGTERM".to_string()),
                healthcheck: Some(HealthcheckProfile {
                    test: vec![
                        "CMD".to_string(),
                        "/entrypoint.sh".to_string(),
                        "healthcheck".to_string()
                    ],
                    interval_ns: Some(10000000000),
                    timeout_ns: Some(3000000000),
                    start_period_ns: Some(5000000000),
                    retries: Some(5),
                }),
                tools: std::collections::BTreeMap::new(),
                tool_details: std::collections::BTreeMap::new(),
                signatures: RuntimeSignatures::default(),
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
    fn parse_image_reference_rejects_disallowed_registry_host() {
        let result = parse_image_reference("localhost/team/image:1.0");
        assert!(result.is_err());
    }

    #[test]
    fn parse_image_reference_normalizes_docker_hub_repository_to_lowercase() {
        let parsed =
            parse_image_reference("docker.io/Library/NgInX:RC1").expect("parse should succeed");
        assert_eq!(parsed.repository, "library/nginx");
        assert_eq!(parsed.tag, "RC1");
        assert_eq!(parsed.normalized, "docker.io/library/nginx:RC1");
    }

    #[test]
    fn parse_image_reference_rejects_unsupported_characters() {
        let result = parse_image_reference("docker.io/library/nginx?latest");
        assert!(result.is_err());
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
    fn parse_github_owner_repo_extracts_owner_and_repo() {
        let parsed = parse_github_owner_repo("https://github.com/example/project")
            .expect("github repo url should parse");
        assert_eq!(parsed.0, "example");
        assert_eq!(parsed.1, "project");
    }

    #[test]
    fn extract_github_url_prefers_repository_matching_image_name() {
        let body = r#"
See docs at https://github.com/localtunnel/localtunnel and source at
https://github.com/n8n-io/n8n for build details.
"#;
        let extracted = extract_github_url(body, "n8nio/n8n");
        assert_eq!(extracted.as_deref(), Some("https://github.com/n8n-io/n8n"));
    }

    #[test]
    fn extract_github_url_rejects_unrelated_repository_links() {
        let body = "See companion project https://github.com/localtunnel/localtunnel for setup.";
        let extracted = extract_github_url(body, "n8nio/n8n");
        assert_eq!(extracted, None);
    }

    #[test]
    fn docs_scan_candidates_prefers_github_readme_api() {
        let candidates = docs_scan_candidates(
            Some("https://hub.docker.com/r/library/postgres"),
            Some("https://github.com/docker-library/postgres"),
        );
        assert_eq!(
            candidates,
            vec!["https://api.github.com/repos/docker-library/postgres/readme".to_string()]
        );
    }

    #[test]
    fn build_docs_request_sets_github_raw_headers() {
        let client = Client::builder().build().expect("client should build");
        let request = build_docs_request(
            &client,
            "https://api.github.com/repos/example/project/readme",
            "agent-skills/1.0",
        )
        .build()
        .expect("request should build");

        assert_eq!(
            request
                .headers()
                .get("accept")
                .and_then(|value| value.to_str().ok()),
            Some("application/vnd.github.v3.raw")
        );
        assert_eq!(
            request
                .headers()
                .get("x-github-api-version")
                .and_then(|value| value.to_str().ok()),
            Some("2022-11-28")
        );
    }

    #[test]
    fn extract_recommended_env_from_docs_reads_environment_table_rows() {
        let markdown = r#"
## Environment Variables

| Variable | Description |
| --- | --- |
| POSTGRES_PASSWORD | Required secret. |
| POSTGRES_DB | Optional database name. |
"#;
        let discovered = extract_recommended_env_from_docs(markdown);
        assert!(discovered.contains(&"POSTGRES_PASSWORD".to_string()));
        assert!(discovered.contains(&"POSTGRES_DB".to_string()));
    }

    #[test]
    fn normalize_image_reference_expands_default_registry_and_namespace() {
        let normalized =
            normalize_image_reference("nginx:1.27").expect("normalization should succeed");
        assert_eq!(normalized, "docker.io/library/nginx:1.27");
    }
}
