to_entries | all(.value.result == "success" or (.key == "dependency-review" and .value.result == "skipped"))
