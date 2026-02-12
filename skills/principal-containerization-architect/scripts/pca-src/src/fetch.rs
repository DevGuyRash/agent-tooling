//! Metadata fetchers for API-first and fallback research.

use std::time::Duration;

use regex::Regex;
use reqwest::blocking::{Client, Response};
use reqwest::header::{ACCEPT, AUTHORIZATION, USER_AGENT, WWW_AUTHENTICATE};
use serde::Deserialize;
use serde_json::Value;
use url::Url;

use crate::error::AppError;
use crate::model::{ImageProfile, Platform};

const DEFAULT_USER_AGENT: &str = "agent-skills-pca/0.1";

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
/// use pca::fetch::fetch_image_profile;
///
/// let profile = fetch_image_profile("nginx:1.27", true)?;
/// assert!(profile.image.contains("nginx"));
/// # Ok::<(), pca::error::AppError>(())
/// ```
pub fn fetch_image_profile(
    image: &str,
    allow_scrape_fallback: bool,
) -> Result<ImageProfile, AppError> {
    let client = Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|error| AppError::InvalidInput {
            reason: format!("failed to build http client: {error}"),
        })?;

    let parsed = parse_image_reference(image)?;
    let mut notes = Vec::new();

    let mut digest: Option<String> = None;
    let mut platforms: Vec<Platform> = Vec::new();
    let mut docs_url: Option<String> = None;
    let mut dockerfile_url: Option<String> = None;

    if parsed.registry == "docker.io" {
        match fetch_docker_hub_metadata(&client, &parsed) {
            Ok(hub) => {
                digest = hub.digest;
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
        match fetch_registry_manifest(&client, &parsed) {
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

    if allow_scrape_fallback && (digest.is_none() || dockerfile_url.is_none()) {
        if let Ok((scraped_digest, scraped_repo_url)) = scrape_hub_page(&client, &parsed.repository)
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

    if docs_url.is_none() && parsed.registry == "docker.io" {
        docs_url = Some(format!("https://hub.docker.com/r/{}", parsed.repository));
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
/// use pca::fetch::fetch_profiles;
///
/// let profiles = fetch_profiles(&["nginx:1.27".to_string()], true)?;
/// assert_eq!(profiles.len(), 1);
/// # Ok::<(), pca::error::AppError>(())
/// ```
pub fn fetch_profiles(
    images: &[String],
    allow_scrape_fallback: bool,
) -> Result<Vec<ImageProfile>, AppError> {
    let mut output = Vec::with_capacity(images.len());
    for image in images {
        output.push(fetch_image_profile(image, allow_scrape_fallback)?);
    }
    Ok(output)
}

fn fetch_docker_hub_metadata(
    client: &Client,
    parsed: &ParsedImageRef,
) -> Result<DockerHubMetadata, AppError> {
    let tag_url = format!(
        "https://hub.docker.com/v2/repositories/{}/tags/{}",
        parsed.repository, parsed.tag
    );
    let tag_response = client
        .get(&tag_url)
        .header(USER_AGENT, DEFAULT_USER_AGENT)
        .send()
        .map_err(|error| AppError::Http {
            url: tag_url.clone(),
            reason: error.to_string(),
        })?;

    if !tag_response.status().is_success() {
        return Err(AppError::Http {
            url: tag_url,
            reason: format!("unexpected status {}", tag_response.status()),
        });
    }

    let tag_payload: DockerHubTagResponse =
        tag_response.json().map_err(|error| AppError::Http {
            url: "https://hub.docker.com/v2/repositories/<repo>/tags/<tag>".to_string(),
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

    let repo_url = format!(
        "https://hub.docker.com/v2/repositories/{}",
        parsed.repository
    );
    let repo_response = client
        .get(&repo_url)
        .header(USER_AGENT, DEFAULT_USER_AGENT)
        .send()
        .map_err(|error| AppError::Http {
            url: repo_url.clone(),
            reason: error.to_string(),
        })?;

    if !repo_response.status().is_success() {
        return Ok(DockerHubMetadata {
            digest,
            platforms,
            docs_url: Some(format!("https://hub.docker.com/r/{}", parsed.repository)),
            dockerfile_url: None,
        });
    }

    let repo_payload: DockerHubRepoResponse =
        repo_response.json().map_err(|error| AppError::Http {
            url: repo_url,
            reason: format!("invalid docker hub repository payload: {error}"),
        })?;

    let dockerfile_url = repo_payload
        .full_description
        .as_deref()
        .and_then(extract_github_url);

    Ok(DockerHubMetadata {
        digest,
        platforms,
        docs_url: Some(format!("https://hub.docker.com/r/{}", parsed.repository)),
        dockerfile_url,
    })
}

fn fetch_registry_manifest(
    client: &Client,
    parsed: &ParsedImageRef,
) -> Result<(Option<String>, Vec<Platform>), AppError> {
    let manifest_url = format!(
        "https://{}/v2/{}/manifests/{}",
        parsed.registry, parsed.repository, parsed.reference
    );

    let response = request_registry(client, &manifest_url, None)?;
    if response.status() == reqwest::StatusCode::UNAUTHORIZED {
        let challenge = response
            .headers()
            .get(WWW_AUTHENTICATE)
            .and_then(|value| value.to_str().ok())
            .ok_or_else(|| AppError::Http {
                url: manifest_url.clone(),
                reason: "registry returned 401 without WWW-Authenticate".to_string(),
            })?;

        let auth = parse_auth_challenge(challenge).ok_or_else(|| AppError::Http {
            url: manifest_url.clone(),
            reason: "failed to parse auth challenge".to_string(),
        })?;

        let token = fetch_bearer_token(client, &auth, &parsed.repository)?;
        let authorized = request_registry(client, &manifest_url, Some(&token))?;
        return parse_manifest_response(&manifest_url, authorized);
    }

    parse_manifest_response(&manifest_url, response)
}

fn parse_manifest_response(
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
    }

    Ok((digest, platforms))
}

fn request_registry(client: &Client, url: &str, token: Option<&str>) -> Result<Response, AppError> {
    let mut request = client
        .get(url)
        .header(USER_AGENT, DEFAULT_USER_AGENT)
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

fn fetch_bearer_token(
    client: &Client,
    challenge: &AuthChallenge,
    repository: &str,
) -> Result<String, AppError> {
    let mut token_url = Url::parse(&challenge.realm).map_err(|error| AppError::Http {
        url: challenge.realm.clone(),
        reason: format!("invalid token realm url: {error}"),
    })?;

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
        .header(USER_AGENT, DEFAULT_USER_AGENT)
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
        url: "token-endpoint".to_string(),
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
) -> Result<(Option<String>, Option<String>), AppError> {
    let url = format!("https://hub.docker.com/r/{repository}");
    let body = client
        .get(&url)
        .header(USER_AGENT, DEFAULT_USER_AGENT)
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
        .to_lowercase();

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
        if first.contains('.') || first.contains(':') || first == "localhost" {
            registry = first.to_string();
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

    let (repository, tag) = match digest {
        Some(_) => {
            let (repo_only, inferred_tag) = split_tag(&repository);
            (repo_only.to_string(), inferred_tag.to_string())
        }
        None => {
            let (repo_only, explicit_tag) = split_tag(&repository);
            (repo_only.to_string(), explicit_tag.to_string())
        }
    };

    let reference = digest.unwrap_or_else(|| tag.clone());
    let normalized = if reference.starts_with("sha256:") {
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
