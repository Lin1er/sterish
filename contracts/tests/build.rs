//! STE-44 — build the contract wasm that `tests/upgrade.rs` needs.
//!
//! # Why a build script and not `contractimport!`
//!
//! Replacing a contract's wasm can only be tested against a real artifact:
//! `env.register(SkillRegistry, ..)` builds a NATIVE contract, and
//! `update_current_contract_wasm` needs bytes that were actually uploaded. So
//! the upgrade tests need `sterish_registry.wasm` et al. to exist at the moment
//! `tests/upgrade.rs` is COMPILED.
//!
//! `contractimport!(file = "../target/wasm32v1-none/release/…")` would be the
//! shorter spelling, but it makes `cargo test` fail outright on any checkout
//! where nobody has run a wasm build first — including a fresh CI runner, where
//! the `Run contract tests` step comes before `Check WASM build`. Reordering the
//! workflow to paper over that would make the test suite depend on the order of
//! two steps in a YAML file, which is not a dependency anyone would think to
//! preserve.
//!
//! Building them here instead keeps a bare `cargo test` working from a clean
//! clone, and keeps the artifacts out of git.
//!
//! # The environment has to be scrubbed
//!
//! The nested build must NOT inherit the outer one's flags. Under
//! `cargo llvm-cov` the parent sets `-C instrument-coverage` in `RUSTFLAGS`,
//! which does not apply to `wasm32v1-none` and fails the nested build; and an
//! inherited `CARGO_TARGET_DIR` would send the artifacts somewhere this script
//! is not looking. Everything that could leak is removed explicitly.

use std::{env, path::PathBuf, process::Command};

/// (cargo package name, wasm file stem). The wasm stem also names the env var
/// the test reads, upper-cased: `sterish_registry` -> `STERISH_REGISTRY_WASM`.
const FIXTURES: &[(&str, &str)] = &[
    ("sterish-registry", "sterish_registry"),
    ("sterish-tokens", "sterish_tokens"),
    // Not upgradeable, on purpose — the stand-in for "a wasm with no upgrade
    // entrypoint", which is the trap that costs upgradeability forever.
    ("sterish-escrow", "sterish_escrow"),
    ("sterish-upgrade-probe", "sterish_upgrade_probe"),
];

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    for path in [
        "../registry/src",
        "../tokens/src",
        "../escrow/src",
        "../upgrade-probe/src",
        "../Cargo.toml",
        "../Cargo.lock",
        "../../rust-toolchain.toml",
    ] {
        println!("cargo:rerun-if-changed={path}");
    }

    // When this crate is itself being compiled for wasm32v1-none (the workspace
    // `cargo build --target wasm32v1-none` in CI), only the empty `src/lib.rs`
    // shell is built. `tests/` is not, so nothing reads these variables and
    // there is nothing to build.
    if env::var("CARGO_CFG_TARGET_ARCH").as_deref() == Ok("wasm32") {
        return;
    }

    let target_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR")).join("wasm");
    let cargo = env::var("CARGO").unwrap_or_else(|_| "cargo".into());

    let mut cmd = Command::new(cargo);
    cmd.current_dir("..") // contracts/
        .arg("build")
        .arg("--release")
        .arg("--target")
        .arg("wasm32v1-none")
        .arg("--target-dir")
        .arg(&target_dir);
    for (package, _) in FIXTURES {
        cmd.arg("--package").arg(package);
    }
    for leaked in [
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_BUILD_RUSTFLAGS",
        "RUSTDOCFLAGS",
        "CARGO_ENCODED_RUSTDOCFLAGS",
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
        "LLVM_PROFILE_FILE",
        "CARGO_TARGET_DIR",
        "CARGO_BUILD_TARGET",
    ] {
        cmd.env_remove(leaked);
    }

    let status = cmd.status().expect("could not run the nested cargo build");
    assert!(
        status.success(),
        "nested wasm build failed ({status}). The upgrade tests cannot run \
         without real artifacts; see contracts/tests/build.rs."
    );

    let release = target_dir.join("wasm32v1-none").join("release");
    for (_, stem) in FIXTURES {
        let wasm = release.join(format!("{stem}.wasm"));
        assert!(
            wasm.is_file(),
            "nested build reported success but did not produce {}",
            wasm.display()
        );
        println!(
            "cargo:rustc-env={}_WASM={}",
            stem.to_uppercase(),
            wasm.display()
        );
    }
}
