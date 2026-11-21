# All runs in this repo

One row per run (1 seed per task). Generated from `analysis/cells.csv` and `analysis/agentshape.csv`; run outputs are in `featurebench/runs/<run>/` and `swebench-pro/runs/<run>/`.

**Subsets.**
- FeatureBench `fresh` (16): no earlier arm of the study had run the task.
- FeatureBench `seen_other_arm` (5): the same task had also run in an earlier arm (baseline/doc/impact), each time in a fresh container.
- SWE-bench Pro `batch1` (5) and `nohint` (7): the 12 early runs, with `prompt.txt`.
- SWE-bench Pro `batch3` (38): run with `prompt_verbatim.txt`.
- SWE-bench Pro `batch4` (11): multi-file tasks run by a teammate on 2026-11-20/21, with `prompt_verbatim.txt` (identical to `prompt.txt` for these tasks).

**Columns.**
- r0 = passed acceptance in round 0. All 82 runs were finally accepted. 78 passed in round 0; 4 FeatureBench runs (command_line, build_gettext, relational, line) passed after one blind round (rounds = 2).
- files / lines = production files and lines in the agent's final diff.
- recall = share of gold added lines reproduced verbatim.
- cost = CLI list-price USD.

| Benchmark | Subset | Runs |
|---|---|---|
| FeatureBench | fresh | 16 |
| FeatureBench | seen_other_arm | 5 |
| SWE-bench Pro | batch1 | 5 |
| SWE-bench Pro | batch3 | 38 |
| SWE-bench Pro | batch4 | 11 |
| SWE-bench Pro | nohint | 7 |

## FeatureBench (21 runs)

| # | Subset | Repo | Task | Run dir | r0 | rounds | final | cost $ | tool calls | files | lines | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | seen_other_arm | mlflow | mlflow | `20261111-161051-mlflow-test_mlflow-s1-goalrw` | pass | 1 | accept | 3.18 | 68 | 22 | 562 | 0.94 |
| 2 | seen_other_arm | mlflow | scorers | `20261111-172824-mlflow-test_scorers-s1-goalrw` | pass | 1 | accept | 2.99 | 78 | 13 | 601 | 0.68 |
| 3 | seen_other_arm | mlflow | git_versioning | `20261111-191937-mlflow-test_git_versioning-s1-goalrw` | pass | 1 | accept | 1.17 | 40 | 6 | 193 | 0.62 |
| 4 | seen_other_arm | sphinx-doc | command_line | `20261111-195214-sphinx-doc-test_command_line-s1-goalrw` | fail | 2 | accept | 0.85 | 20 | 2 | 273 | 0.97 |
| 5 | fresh | sphinx-doc | ext_doctest | `20261111-200405-sphinx-doc-test_ext_doctest-s1-goalrw` | pass | 1 | accept | 1.11 | 28 | 2 | 428 | 0.99 |
| 6 | fresh | sphinx-doc | ext_math | `20261111-201158-sphinx-doc-test_ext_math-s1-goalrw` | pass | 1 | accept | 4.49 | 95 | 21 | 1036 | 0.96 |
| 7 | fresh | sphinx-doc | build_gettext | `20261111-202801-sphinx-doc-test_build_gettext-s1-goalrw` | fail | 2 | accept | 4.36 | 90 | 30 | 755 | 0.96 |
| 8 | fresh | sphinx-doc | ext_napoleon_docstring | `20261111-204942-sphinx-doc-test_ext_napoleon_docstring-s1-goalrw` | pass | 1 | accept | 3.56 | 68 | 15 | 1287 | 0.98 |
| 9 | fresh | pandas-dev | describe | `20261112-091735-pandas-dev-test_describe-s1-goalrw` | pass | 1 | accept | 7.83 | 128 | 33 | 2326 | 0.96 |
| 10 | fresh | pandas-dev | formats | `20261112-173352-pandas-dev-test_formats-s1-goalrw` | pass | 1 | accept | 6.69 | 139 | 17 | 3904 | 0.98 |
| 11 | fresh | pandas-dev | groupby_shift_diff | `20261112-222037-pandas-dev-test_groupby_shift_diff-s1-goalrw` | pass | 1 | accept | 6.01 | 120 | 25 | 1921 | 0.99 |
| 12 | fresh | astropy | compression_failures | `20261113-103337-astropy-test_compression_failures-s1-goalrw` | pass | 1 | accept | 1.55 | 36 | 12 | 549 | 0.89 |
| 13 | seen_other_arm | astropy | containers | `20261113-124909-astropy-test_containers-s1-goalrw` | pass | 1 | accept | 1.28 | 17 | 2 | 486 | 0.72 |
| 14 | fresh | astropy | vo | `20261113-125825-astropy-test_vo-s1-goalrw` | pass | 1 | accept | 2.14 | 50 | 11 | 548 | 0.91 |
| 15 | fresh | mwaskom | relational | `20261113-214032-mwaskom-test_relational-s1-goalrw` | fail | 2 | accept | 2.09 | 50 | 8 | 586 | 0.96 |
| 16 | fresh | mwaskom | regression | `20261113-220252-mwaskom-test_regression-s1-goalrw` | pass | 1 | accept | 1.22 | 25 | 5 | 637 | 1.00 |
| 17 | fresh | mwaskom | line | `20261113-221325-mwaskom-test_line-s1-goalrw` | fail | 2 | accept | 1.35 | 37 | 10 | 221 | 1.00 |
| 18 | fresh | mwaskom | scales | `20261113-222522-mwaskom-test_scales-s1-goalrw` | pass | 1 | accept | 1.22 | 20 | 4 | 592 | 0.99 |
| 19 | fresh | pydata | backends_chunks | `20261117-125746-pydata-test_backends_chunks-s1-goalrw` | pass | 1 | accept | 0.71 | 21 | 6 | 166 | 0.79 |
| 20 | fresh | pydata | treenode | `20261117-140911-pydata-test_treenode-s1-goalrw` | pass | 1 | accept | 0.91 | 20 | 6 | 428 | 0.94 |
| 21 | fresh | pydata | range_index | `20261117-152828-pydata-test_range_index-s1-goalrw` | pass | 1 | accept | 2.49 | 59 | 22 | 777 | 0.99 |

## SWE-bench Pro (61 runs)

| # | Subset | Repo | Task | Run dir | r0 | rounds | final | cost $ | tool calls | files | lines | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | batch1 | element-hq | element-hq-33e8edb3 | `20261103-182535-element-hq-element-web-33e8edb3d508d6eefb354819ca693b7accc69-s1` | pass | 1 | accept | 0.40 | 7 | 1 | 291 | 0.23 |
| 2 | batch1 | navidrome | navidrome-55730514 | `20261103-183212-navidrome-navidrome-55730514ea59d5f1d0b8e3f8745569c29bdbf7b4-s1` | pass | 1 | accept | 0.36 | 7 | 4 | 219 | 0.32 |
| 3 | batch1 | future-architect | future-architect-1832b4ee | `20261103-185531-future-architect-vuls-1832b4ee3a20177ad313d806983127cb6e53f5-s1` | pass | 1 | accept | 0.54 | 11 | 7 | 288 | 0.53 |
| 4 | batch1 | ansible | ansible-40ade1f8 | `20261103-191010-ansible-ansible-40ade1f84b8bb10a63576b0ac320c13f57c87d34-s1` | pass | 1 | accept | 0.99 | 9 | 1 | 596 | 0.65 |
| 5 | batch1 | ansible | ansible-c1f2df47 | `20261103-193323-ansible-ansible-c1f2df47538b884a43320f53e787197793b105e8-s1` | pass | 1 | accept | 0.52 | 11 | 1 | 446 | 0.86 |
| 6 | nohint | protonmail | protonmail-0d0267c4 | `20261104-230753-protonmail-webclients-0d0267c4438cf378bda90bc85eed3a3615871a-s1` | pass | 1 | accept | 0.21 | 5 | 3 | 24 | 0.02 |
| 7 | nohint | protonmail | protonmail-8be4f6cb | `20261105-010938-protonmail-webclients-8be4f6cb9380fcd2e67bcb18cef931ae0d4b86-s1` | pass | 1 | accept | 1.16 | 26 | 29 | 277 | 0.49 |
| 8 | nohint | protonmail | protonmail-d8ff92b4 | `20261105-092014-protonmail-webclients-d8ff92b414775565f496b830c9eb6cc5fa9620-s1` | pass | 1 | accept | 0.47 | 12 | 8 | 450 | 0.44 |
| 9 | nohint | protonmail | protonmail-bf2e89c0 | `20261105-105630-protonmail-webclients-bf2e89c0c488ae1a87d503e5b09fe9dd2f2a63-s1` | pass | 1 | accept | 0.52 | 13 | 4 | 14 | 0.18 |
| 10 | nohint | protonmail | protonmail-32ff1099 | `20261105-122303-protonmail-webclients-32ff10999a06455cb2147f6873d627456924ae-s1` | pass | 1 | accept | 0.12 | 3 | 1 | 6 | 0.03 |
| 11 | nohint | protonmail | protonmail-f080ffc3 | `20261105-162521-protonmail-webclients-f080ffc38e2ad7bddf2e93e5193e82c20c7a11-s1` | pass | 1 | accept | 0.46 | 13 | 4 | 42 | 0.16 |
| 12 | nohint | protonmail | protonmail-08bb0991 | `20261105-171356-protonmail-webclients-08bb09914d0d37b0cd6376d4cab5b77728a43e-s1` | pass | 1 | accept | 0.40 | 10 | 2 | 177 | 0.24 |
| 13 | batch3 | flipt-io | flipt-io-524f2773 | `20261118-233209-flipt-io-flipt-524f277313606f8cd29b299617d6565c01642e15-s1-verb` | pass | 1 | accept | 0.93 | 31 | 7 | 171 | 0.70 |
| 14 | batch3 | gravitational | gravitational-82185f23 | `20261119-000523-gravitational-teleport-82185f232ae8974258397e121b3bc2ed0c372-s1-verb` | pass | 1 | accept | 0.38 | 12 | 3 | 161 | 0.84 |
| 15 | batch3 | navidrome | navidrome-31799662 | `20261119-002450-navidrome-navidrome-31799662706fedddf5bcc1a76b50409d1f91d327-s1-verb` | pass | 1 | accept | 0.15 | 3 | 2 | 19 | 0.07 |
| 16 | batch3 | internetarchive | internetarchive-7c8dc180 | `20261119-004325-internetarchive-openlibrary-7c8dc180281491ccaa1b4b4351850632-s1-verb` | pass | 1 | accept | 0.23 | 6 | 1 | 144 | 0.07 |
| 17 | batch3 | flipt-io | flipt-io-b2393f07 | `20261119-151358-flipt-io-flipt-b2393f07d893024ab1e47ea2081e0289e1f9d56f-s1-verb` | pass | 1 | accept | 0.41 | 16 | 4 | 69 | 0.31 |
| 18 | batch3 | element-hq | element-hq-772df302 | `20261119-154934-element-hq-element-web-772df3021201d9c73835a626df8dcb6334ad9-s1-verb` | pass | 1 | accept | 0.51 | 14 | 3 | 94 | 0.67 |
| 19 | batch3 | element-hq | element-hq-2760bfc8 | `20261119-160400-element-hq-element-web-2760bfc8369f1bee640d6d7a7e910783143d4-s1-verb` | pass | 1 | accept | 0.44 | 12 | 1 | 135 | 0.85 |
| 20 | batch3 | navidrome | navidrome-6bd4c0f6 | `20261119-162008-navidrome-navidrome-6bd4c0f6bfa653e9b8b27cfdc2955762d371d6e9-s1-verb` | pass | 1 | accept | 0.81 | 21 | 6 | 166 | 0.51 |
| 21 | batch3 | ansible | ansible-5d253a13 | `20261119-165531-ansible-ansible-5d253a13807e884b7ce0b6b57a963a45e2f0322c-s1-verb` | pass | 1 | accept | 0.37 | 12 | 1 | 101 | 0.72 |
| 22 | batch3 | future-architect | future-architect-50580f6e | `20261119-170534-future-architect-vuls-50580f6e98eeb36f53f27222f7f4fdfea0b21e-s1-verb` | pass | 1 | accept | 0.33 | 7 | 1 | 99 | 0.75 |
| 23 | batch3 | gravitational | gravitational-dd397795 | `20261119-172359-gravitational-teleport-dd3977957a67bedaf604ad6ca255ba8c7b670-s1-verb` | pass | 1 | accept | 0.16 | 8 | 1 | 8 | 0.06 |
| 24 | batch3 | protonmail | protonmail-863d524b | `20261119-175419-protonmail-webclients-863d524b5717b9d33ce08a0f0535e3fd8e8d1e-s1-verb` | pass | 1 | accept | 0.38 | 10 | 2 | 109 | 0.27 |
| 25 | batch3 | flipt-io | flipt-io-db1c3b10 | `20261119-183101-flipt-io-flipt-db1c3b100e231c62f0c90c2ab037614f20a2a63b-s1-verb` | pass | 1 | accept | 0.33 | 12 | 3 | 108 | 1.00 |
| 26 | batch3 | qutebrowser | qutebrowser-16de0540 | `20261119-185147-qutebrowser-qutebrowser-16de05407111ddd82fa12e54389d53236248-s1-verb` | pass | 1 | accept | 0.39 | 11 | 1 | 60 | 0.76 |
| 27 | batch3 | protonmail | protonmail-fc9d535e | `20261119-192729-protonmail-webclients-fc9d535e9beb3ae30a52a7146398cadfd6e306-s1-verb` | pass | 1 | accept | 0.39 | 14 | 1 | 41 | 0.09 |
| 28 | batch3 | gravitational | gravitational-53814a2d | `20261119-200719-gravitational-teleport-53814a2d600ccd74c1e9810a567563432b983-s1-verb` | pass | 1 | accept | 0.24 | 7 | 1 | 45 | 0.24 |
| 29 | batch3 | NodeBB | NodeBB-6489e9fd | `20261119-202002-NodeBB-NodeBB-6489e9fd9ed16ea743cc5627f4d86c72fbdb3a8a-s1-verb` | pass | 1 | accept | 0.62 | 21 | 4 | 85 | 0.49 |
| 30 | batch3 | qutebrowser | qutebrowser-ec2dcfce | `20261119-202919-qutebrowser-qutebrowser-ec2dcfce9eee9f808efc17a1b99e227fc442-s1-verb` | pass | 1 | accept | 0.40 | 16 | 1 | 38 | 0.84 |
| 31 | batch3 | qutebrowser | qutebrowser-01d1d149 | `20261119-203338-qutebrowser-qutebrowser-01d1d1494411380d97cac14614a829d3a69c-s1-verb` | pass | 1 | accept | 0.25 | 8 | 2 | 40 | 0.38 |
| 32 | batch3 | navidrome | navidrome-6c6223f2 | `20261119-203908-navidrome-navidrome-6c6223f2f9db2c8c253e0d40a192e3519c9037d1-s1-verb` | pass | 1 | accept | 0.19 | 6 | 1 | 8 | 0.07 |
| 33 | batch3 | flipt-io | flipt-io-abaa5953 | `20261119-205731-flipt-io-flipt-abaa5953795afb9c621605bb18cb32ac48b4508c-s1-verb` | pass | 1 | accept | 0.21 | 9 | 1 | 13 | 0.14 |
| 34 | batch3 | internetarchive | internetarchive-fdbc0d8f | `20261119-211139-internetarchive-openlibrary-fdbc0d8f418333c7e575c40b661b582c-s1-verb` | pass | 1 | accept | 0.19 | 6 | 1 | 12 | 0.05 |
| 35 | batch3 | protonmail | protonmail-0200ce0f | `20261119-214033-protonmail-webclients-0200ce0fc1d4dbd35178c10d440a284c82ecc8-s1-verb` | pass | 1 | accept | 0.37 | 13 | 1 | 75 | 0.20 |
| 36 | batch3 | navidrome | navidrome-8d56ec89 | `20261119-221605-navidrome-navidrome-8d56ec898e776e7e53e352cb9b25677975787ffc-s1-verb` | pass | 1 | accept | 0.31 | 10 | 1 | 55 | 0.66 |
| 37 | batch3 | protonmail | protonmail-1501eb76 | `20261119-224858-protonmail-webclients-1501eb765873b2884b6f1944fd242ecfc9d6b1-s1-verb` | pass | 1 | accept | 0.33 | 7 | 4 | 58 | 0.71 |
| 38 | batch3 | internetarchive | internetarchive-3f580a5f | `20261119-231423-internetarchive-openlibrary-3f580a5f244c299d936d73d9e327ba87-s1-verb` | pass | 1 | accept | 0.19 | 7 | 1 | 13 | 0.04 |
| 39 | batch3 | qutebrowser | qutebrowser-cf06f4e3 | `20261119-232354-qutebrowser-qutebrowser-cf06f4e3708f886032d4d2a30108c2fddb04-s1-verb` | pass | 1 | accept | 0.29 | 10 | 1 | 58 | 0.42 |
| 40 | batch3 | flipt-io | flipt-io-f743945d | `20261119-234028-flipt-io-flipt-f743945d599b178293e89e784b3b2374b1026430-s1-verb` | pass | 1 | accept | 0.26 | 8 | 4 | 51 | 0.86 |
| 41 | batch3 | gravitational | gravitational-47530e1f | `20261120-001040-gravitational-teleport-47530e1fd8bfb84ec096ebcbbc29990f30829-s1-verb` | pass | 1 | accept | 0.25 | 7 | 1 | 48 | 0.44 |
| 42 | batch3 | ansible | ansible-29aea9ff | `20261120-002756-ansible-ansible-29aea9ff3466e4cd2ed00524b9e56738d568ce8b-s1-verb` | pass | 1 | accept | 0.21 | 5 | 2 | 58 | 0.94 |
| 43 | batch3 | flipt-io | flipt-io-72d06db1 | `20261120-003733-flipt-io-flipt-72d06db14d58692bfb4d07b1aa745a37b35956f3-s1-verb` | pass | 1 | accept | 0.19 | 4 | 1 | 49 | 0.70 |
| 44 | batch3 | qutebrowser | qutebrowser-0aa57e4f | `20261120-005434-qutebrowser-qutebrowser-0aa57e4f7243024fa4bba8853306691b5dbd-s1-verb` | pass | 1 | accept | 0.31 | 8 | 1 | 34 | 0.69 |
| 45 | batch3 | flipt-io | flipt-io-c1fd7a81 | `20261120-105136-flipt-io-flipt-c1fd7a81ef9f23e742501bfb26d914eb683262aa-s1-verb` | pass | 1 | accept | 0.44 | 16 | 1 | 42 | 0.73 |
| 46 | batch3 | element-hq | element-hq-f14374a5 | `20261120-111500-element-hq-element-web-f14374a51c153f64f313243f2df6ea4971db4-s1-verb` | pass | 1 | accept | 0.16 | 5 | 1 | 9 | 0.00 |
| 47 | batch3 | future-architect | future-architect-abd80417 | `20261120-112534-future-architect-vuls-abd80417728b16c6502067914d27989ee575f0-s1-verb` | pass | 1 | accept | 0.28 | 8 | 1 | 36 | 0.16 |
| 48 | batch3 | future-architect | future-architect-5af1a227 | `20261120-114619-future-architect-vuls-5af1a227339e46c7abf3f2815e4c636a0c0109-s1-verb` | pass | 1 | accept | 0.45 | 11 | 2 | 85 | 0.09 |
| 49 | batch3 | future-architect | future-architect-999529a0 | `20261120-121707-future-architect-vuls-999529a05b202b0fd29c6fca5039a4c47a3766-s1-verb` | pass | 1 | accept | 0.32 | 5 | 1 | 220 | 0.56 |
| 50 | batch3 | protonmail | protonmail-3a6790f4 | `20261120-123925-protonmail-webclients-3a6790f480309130b5d6332dce6c9d5ccca13e-s1-verb` | pass | 1 | accept | 0.29 | 10 | 1 | 11 | 0.04 |
| 51 | batch4 | ansible | ansible-3b823d90 | `20261120-222719-ansible-ansible-3b823d908e8a5d17674f8c26d337d3114b7493b1-s1-verb` | pass | 1 | accept | 0.22 | 7 | 6 | 38 | 0.61 |
| 52 | batch4 | navidrome | navidrome-d5df102f | `20261120-223059-navidrome-navidrome-d5df102f9f97c21715c756069c9e141da2a422dc-s1-verb` | pass | 1 | accept | 0.16 | 5 | 1 | 6 | 0.12 |
| 53 | batch4 | protonmail | protonmail-c8117f44 | `20261120-225307-protonmail-webclients-c8117f446c3d1d7e117adc6e0e46b0ece9b0b9-s1-verb` | pass | 1 | accept | 0.40 | 12 | 3 | 79 | 0.58 |
| 54 | batch4 | flipt-io | flipt-io-c12967bc | `20261120-230751-flipt-io-flipt-c12967bc73fdf02054cf3ef8498c05e25f0a18c0-s1-verb` | pass | 1 | accept | 0.16 | 6 | 2 | 16 | 0.16 |
| 55 | batch4 | flipt-io | flipt-io-b2170346 | `20261120-231817-flipt-io-flipt-b2170346dc37cf42fda1386cd630f24821ad2ac5-s1-verb` | pass | 1 | accept | 0.16 | 7 | 1 | 3 | 0.10 |
| 56 | batch4 | ansible | ansible-164881d8 | `20261120-233108-ansible-ansible-164881d871964aa64e0f911d03ae270acbad253c-s1-verb` | pass | 1 | accept | 0.24 | 7 | 1 | 31 | 0.22 |
| 57 | batch4 | navidrome | navidrome-09ae41a2 | `20261120-233815-navidrome-navidrome-09ae41a2da66264c60ef307882362d2e2d8d8b89-s1-verb` | pass | 1 | accept | 0.11 | 2 | 1 | 13 | 0.18 |
| 58 | batch4 | future-architect | future-architect-be7b9114 | `20261120-234936-future-architect-vuls-be7b9114cc9545e68fb0ee7bc63d7ec53d1a00-s1-verb` | pass | 1 | accept | 0.18 | 9 | 3 | 16 | 0.26 |
| 59 | batch4 | future-architect | future-architect-4b680b99 | `20261121-000134-future-architect-vuls-4b680b996061044e93ef5977a081661665d336-s1-verb` | pass | 1 | accept | 0.20 | 7 | 2 | 43 | 0.94 |
| 60 | batch4 | protonmail | protonmail-01b519cd | `20261121-001559-protonmail-webclients-01b519cd49e6a24d9a05d2eb97f54e42074007-s1-verb` | pass | 1 | accept | 0.33 | 12 | 4 | 43 | 0.42 |
| 61 | batch4 | protonmail | protonmail-708ed4a2 | `20261121-115132-protonmail-webclients-708ed4a299711f0fa79a907cc5847cfd39c0fc-s1-verb` | pass | 1 | accept | 0.14 | 3 | 1 | 17 | 0.04 |

