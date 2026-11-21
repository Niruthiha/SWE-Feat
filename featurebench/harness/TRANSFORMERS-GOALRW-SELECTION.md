# Transformers goal-only batch: selection (2026-11-12)
User: "transformers, pick 4 at random 2 localized 2 scattered big tasks".
Pool: all 28 huggingface/transformers tasks in featurebench/inventory/tasks.csv (eligibility filter not applied, same as pandas).
big = impl_loc >= repo median (296) -> 14 tasks. localized = dos_pkg < 0.4 (5 tasks); scattered = dos_pkg >= 0.6 (6 tasks).
random.Random(20261112).sample over each sorted pool; first 2 of each:
  localized: test_feature_extraction_auto.13dd67ea (impl 702, 17 files, 3 pkgs, dos_pkg .359)
             test_video_processing_auto.c41f8df4  (impl 748, 12 files, 2 pkgs, dos_pkg .348)
  scattered: test_modeling_speech_encoder_decoder.b0d78d76 (impl 464, 9 files, 5 pkgs, dos_pkg .695)
             test_processing_grounding_dino.3d24a7e6       (impl 1697, 12 files, 4 pkgs, dos_pkg .677)
Backups in drawn order (if a pick is infeasible): localized test_tests_fetcher, test_candidate_generator, test_processing_samhq;
  scattered test_processing_git, test_modeling_colpali, test_tokenization_prophetnet, test_processing_owlvit.
Note: dos_pkg uses source root src/transformers/models (inventory decisions.md).

## 2026-11-13 substitutions
- test_feature_extraction_auto (localized) DROPPED: gold fails offline (5/10 F2P + P2P tokenizer tests need the Hugging Face Hub; acceptance runs with --network none). Moved to tasks/_dropped/. Replaced by the first localized backup, test_tests_fetcher.e1abe0dd (utils/tests_fetcher.py, functions removed from an existing file; test.patch has no hub ids).
- 2026-11-13: batch ABANDONED (gold fails offline across picks); user chose to switch repo.
