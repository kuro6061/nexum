// Required for LLM outputs > ~2MB (common with long-context models)
// This is the "Claim Check" pattern - Temporal docs recommend it but don't provide it
import { PayloadConverter, METADATA_ENCODING_KEY } from '@temporalio/common';
// ... ~150 lines to implement S3/GCS-backed payload storage
// Must handle: encode, decode, S3 upload, S3 download, error handling
// Must be deployed as a separate "Codec Server" process
// Reference: https://docs.temporal.io/self-hosted-guide/codec-server
export class LargePayloadDataConverter implements PayloadConverter {
  // ~150 lines omitted for brevity
  // Full implementation requires: AWS SDK, S3 bucket config, IAM roles
}
