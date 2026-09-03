#![no_std]
//! Cross-contract integration tests for Sterish (STE-12).
//!
//! This crate intentionally ships **no library code**. Its only purpose is to be
//! a workspace member that owns `tests/integration.rs`, where the Registry, the
//! USDC escrow and the soulbound tokens contract are deployed together into one
//! `Env` and driven end to end.
//!
//! It is `#![no_std]` so that `cargo build --target wasm32v1-none --release`
//! (which builds every workspace member) keeps working: `wasm32v1-none` has no
//! `std`, and an implicit `extern crate std` would fail to link there.
