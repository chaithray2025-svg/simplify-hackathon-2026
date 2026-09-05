#!/usr/bin/env bash
# Create the real DynamoDB tables + S3 bucket for the dynamodb backend.
# Run ONLY after `aws sso login --profile workshop` succeeds.
# Cost: PAY_PER_REQUEST tables + a near-empty bucket = cents. Safe for the US$20 budget.
#
#   ./scripts/provision_aws.sh            # create
#   ./scripts/provision_aws.sh teardown  # delete everything it made

set -euo pipefail

PROFILE="${AWS_PROFILE:-workshop}"
REGION="${AWS_DEFAULT_REGION:-ap-southeast-1}"

T_REVIEWS="${DDB_TABLE_REVIEWS:-simplifynext_reviews}"
T_TRENDS="${DDB_TABLE_TRENDS:-simplifynext_trends}"
T_ADVICE="${DDB_TABLE_ADVICE:-simplifynext_advice}"
T_REPLIES="${DDB_TABLE_REPLIES:-simplifynext_replies}"
T_FEEDBACK="${DDB_TABLE_FEEDBACK:-simplifynext_feedback}"
BUCKET="${S3_BUCKET_RAW:-simplifynext-raw-reviews}"

AWS="aws --profile ${PROFILE} --region ${REGION}"

simple_table () {
  local name="$1"
  echo "creating table ${name} ..."
  $AWS dynamodb create-table \
    --table-name "${name}" \
    --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST >/dev/null || echo "  (already exists, skipping)"
}

reviews_table () {
  echo "creating table ${T_REVIEWS} (with GSI1) ..."
  $AWS dynamodb create-table \
    --table-name "${T_REVIEWS}" \
    --attribute-definitions \
      AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes \
      "IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}" \
    --billing-mode PAY_PER_REQUEST >/dev/null || echo "  (already exists, skipping)"
}

create_all () {
  reviews_table
  simple_table "${T_TRENDS}"
  simple_table "${T_ADVICE}"
  simple_table "${T_REPLIES}"
  simple_table "${T_FEEDBACK}"

  echo "creating bucket ${BUCKET} ..."
  $AWS s3api create-bucket --bucket "${BUCKET}" \
    --create-bucket-configuration LocationConstraint="${REGION}" >/dev/null \
    || echo "  (already exists or owned, skipping)"
  $AWS s3api put-public-access-block --bucket "${BUCKET}" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

  echo "done. set STORAGE_BACKEND=dynamodb in .env to use it."
}

teardown_all () {
  for t in "${T_REVIEWS}" "${T_TRENDS}" "${T_ADVICE}" "${T_REPLIES}" "${T_FEEDBACK}"; do
    echo "deleting table ${t} ..."
    $AWS dynamodb delete-table --table-name "${t}" >/dev/null || echo "  (not found)"
  done
  echo "emptying + deleting bucket ${BUCKET} ..."
  $AWS s3 rm "s3://${BUCKET}" --recursive || true
  $AWS s3api delete-bucket --bucket "${BUCKET}" || echo "  (not found)"
  echo "teardown done."
}

case "${1:-create}" in
  create) create_all ;;
  teardown) teardown_all ;;
  *) echo "usage: $0 [create|teardown]"; exit 2 ;;
esac
