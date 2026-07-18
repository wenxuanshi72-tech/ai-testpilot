# SUT API Acceptance Traceability

Status: Phase 3 executed traceability baseline

Manual source: `test-specs/api/sut_auth_api_cases.yaml`. Executable source: `tests/api/test_sut_auth_api.py`. Run and request evidence: ignored `artifacts/logs/phase3/`.

| Requirement IDs                      | Case ID                 | Pytest test                                               | Result                          | Defect         |
| ------------------------------------ | ----------------------- | --------------------------------------------------------- | ------------------------------- | -------------- |
| `AUTH-HEALTH-001`                    | `API-AUTH-HEALTH-001`   | `test_health`                                             | PASS                            | —              |
| `AUTH-REG-001/003; AUTH-SESSION-001` | `API-AUTH-REGISTER-001` | `test_register_valid_user`                                | PASS                            | —              |
| `AUTH-REG-005`                       | `API-AUTH-REGISTER-002` | `test_reject_duplicate_username`                          | PASS                            | —              |
| `AUTH-REG-001; AUTH-ERROR-001`       | `API-AUTH-REGISTER-003` | `test_reject_missing_username`                            | PASS                            | —              |
| `AUTH-REG-003; AUTH-ERROR-001`       | `API-AUTH-REGISTER-004` | `test_reject_missing_password`                            | PASS                            | —              |
| `AUTH-HTTP-001`                      | `API-AUTH-REGISTER-005` | `test_reject_non_json_request`                            | PASS                            | —              |
| `AUTH-HTTP-002`                      | `API-AUTH-REGISTER-006` | `test_reject_malformed_json`                              | PASS                            | —              |
| `AUTH-REG-002`                       | `API-AUTH-REGISTER-007` | `test_reject_illegal_username`                            | PASS                            | —              |
| `REQ-AUTH-USERNAME-001`              | `API-AUTH-REGISTER-008` | `test_reject_long_username`                               | PASS                            | —              |
| `AUTH-REG-003`                       | `API-AUTH-REGISTER-009` | `test_reject_weak_password`                               | PASS                            | —              |
| `AUTH-LOGIN-001; AUTH-SESSION-001`   | `API-AUTH-LOGIN-001`    | `test_login_success`                                      | PASS                            | —              |
| `AUTH-LOGIN-002`                     | `API-AUTH-LOGIN-002`    | `test_reject_wrong_password`                              | PASS                            | —              |
| `AUTH-LOGIN-002`                     | `API-AUTH-LOGIN-003`    | `test_reject_nonexistent_user`                            | PASS                            | —              |
| `AUTH-ME-001; AUTH-SESSION-002`      | `API-AUTH-ME-001`       | `test_authenticated_me`                                   | PASS                            | —              |
| `AUTH-ME-002`                        | `API-AUTH-ME-002`       | `test_unauthenticated_me`                                 | PASS                            | —              |
| `AUTH-LOGOUT-001`                    | `API-AUTH-LOGOUT-001`   | `test_logout`                                             | PASS                            | —              |
| `AUTH-LOGOUT-001; AUTH-ME-002`       | `API-AUTH-SESSION-001`  | `test_logout_invalidates_session`                         | PASS                            | —              |
| `AUTH-SESSION-002; AUTH-ME-001`      | `API-AUTH-SESSION-002`  | `test_cookie_maintains_session`                           | PASS                            | —              |
| `AUTH-ERROR-001`                     | `API-AUTH-REQUEST-001`  | `test_request_id_propagation`                             | PASS                            | —              |
| `AUTH-ERROR-001`                     | `API-AUTH-ERROR-001`    | `test_uniform_error_envelope`                             | PASS                            | —              |
| `REQ-AUTH-USERNAME-001`              | `API-AUTH-SEED-001`     | `test_formal_requirement_rejects_five_character_username` | XFAIL: expected 400, actual 201 | `BUG-AUTH-001` |

Each evidence record uses the same case ID as the manual and executable sources. Phase 3 records the defect identifier and evidence only; it does not create the later formal Markdown/JSON bug artifact.
