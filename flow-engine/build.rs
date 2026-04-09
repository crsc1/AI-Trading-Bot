fn main() {
    prost_build::compile_protos(
        &["../frontend/src/proto/market.proto"],
        &["../frontend/src/proto/"],
    )
    .expect("Failed to compile protobuf schema");
}
