from typing import Any

try:
    from scenedetect import ContentDetector, SceneManager, open_video
except ImportError:
    pass  # Allow importing module even if scenedetect is missing in some environments

try:
    pass
except ImportError:
    pass


def markers_to_segments(markers: list) -> list[tuple[float, float]]:
    """
    Convert ScanMarker objects or dicts to (start, end) tuples.

    Args:
        markers: List of marker objects (like ScanMarker) or dicts.

    Returns:
        List of (start_time, end_time) tuples.
    """
    segments = []
    for m in markers:
        if isinstance(m, dict):
            segments.append((float(m["start_time"]), float(m["end_time"])))
        elif hasattr(m, "start_time") and hasattr(m, "end_time"):
            segments.append((float(m.start_time), float(m.end_time)))
        else:
            raise ValueError(f"Unknown marker format: {m}")
    return segments


class AccuracyEvaluator:
    """
    A Ground Truth extraction and accuracy evaluation module for the ChannelDNA project.
    """

    def extract_ground_truth(
        self, video_path: str, merge_gap: float = 3.0
    ) -> list[tuple[float, float]]:
        """
        Extract Ground Truth from edited YouTube videos.
        Finds cut points using PySceneDetect and converts them into highlight segments.
        Adjacent cuts within `merge_gap` seconds are merged into a single segment.

        Args:
            video_path: Path to the edited video file.
            merge_gap: Maximum gap (in seconds) between cuts to consider them part of the same segment.

        Returns:
            List of (start_time, end_time) tuples representing ground truth highlight segments.
        """
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        scene_manager.detect_scenes(video)

        scene_list = scene_manager.get_scene_list()

        # Extract cuts (boundaries between scenes)
        cuts = [scene[0].get_seconds() for scene in scene_list[1:]]

        if not cuts:
            return []

        # Group cuts into segments
        segments = []
        current_start = cuts[0]
        current_end = cuts[0]

        for cut in cuts[1:]:
            if cut - current_end <= merge_gap:
                current_end = cut
            else:
                segments.append((current_start, current_end))
                current_start = cut
                current_end = cut

        segments.append((current_start, current_end))

        return segments

    def compute_iou(self, pred: tuple[float, float], gt: tuple[float, float]) -> float:
        """
        Compute Intersection over Union (IoU) between a predicted marker and a ground truth marker.

        Args:
            pred: Tuple of (start_time, end_time) for the prediction.
            gt: Tuple of (start_time, end_time) for the ground truth.

        Returns:
            IoU score as a float between 0.0 and 1.0.
        """
        p_start, p_end = pred
        g_start, g_end = gt

        intersection_start = max(p_start, g_start)
        intersection_end = min(p_end, g_end)

        intersection_duration = max(0.0, intersection_end - intersection_start)

        pred_duration = max(0.0, p_end - p_start)
        gt_duration = max(0.0, g_end - g_start)
        union_duration = pred_duration + gt_duration - intersection_duration

        if union_duration <= 0.0:
            return 0.0

        return intersection_duration / union_duration

    def match_markers(
        self,
        predictions: list[tuple[float, float]],
        ground_truth: list[tuple[float, float]],
    ) -> list[tuple[int, int, float]]:
        """
        Find the best 1-to-1 matching using greedy IoU matching (highest IoU first).

        Args:
            predictions: List of (start, end) predicted markers.
            ground_truth: List of (start, end) GT markers.

        Returns:
            List of tuples (pred_index, gt_index, iou_score).
        """
        ious = []
        for i, p in enumerate(predictions):
            for j, g in enumerate(ground_truth):
                iou = self.compute_iou(p, g)
                if iou > 0:
                    ious.append((iou, i, j))

        # Sort by highest IoU
        ious.sort(key=lambda x: x[0], reverse=True)

        matches = []
        matched_preds = set()
        matched_gts = set()

        for iou, i, j in ious:
            if i not in matched_preds and j not in matched_gts:
                matches.append((i, j, iou))
                matched_preds.add(i)
                matched_gts.add(j)

        return matches

    def evaluate(
        self,
        predictions: list[tuple[float, float]],
        ground_truth: list[tuple[float, float]],
        iou_thresholds: list[float] = None,
    ) -> dict[str, Any]:
        """
        Calculate metrics at multiple IoU thresholds.

        Args:
            predictions: List of predicted segments.
            ground_truth: List of GT segments.
            iou_thresholds: List of thresholds to compute metrics for. Defaults to [0.3, 0.5, 0.7].

        Returns:
            Dictionary containing metrics for each threshold.
        """
        if iou_thresholds is None:
            iou_thresholds = [0.3, 0.5, 0.7]

        matches = self.match_markers(predictions, ground_truth)
        results = {}

        for thresh in iou_thresholds:
            valid_matches = [m for m in matches if m[2] >= thresh]

            tp = len(valid_matches)
            fp = len(predictions) - tp
            fn = len(ground_truth) - tp

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            avg_iou = sum(m[2] for m in valid_matches) / tp if tp > 0 else 0.0

            results[f"iou_{thresh}"] = {
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "average_iou": avg_iou,
            }

        return results

    def compare_ab(
        self,
        before_markers: list[tuple[float, float]],
        after_markers: list[tuple[float, float]],
        ground_truth: list[tuple[float, float]],
    ) -> dict[str, Any]:
        """
        Compute metrics for both 'before' and 'after' marker sets against the same GT.

        Args:
            before_markers: Initial set of predicted markers.
            after_markers: New set of predicted markers.
            ground_truth: Ground truth markers.

        Returns:
            Comparison dictionary with before/after metrics and deltas.
        """
        before_metrics = self.evaluate(before_markers, ground_truth)
        after_metrics = self.evaluate(after_markers, ground_truth)

        f1_deltas = {}
        for thresh_key in before_metrics.keys():
            b_f1 = before_metrics[thresh_key]["f1_score"]
            a_f1 = after_metrics[thresh_key]["f1_score"]
            f1_deltas[thresh_key] = a_f1 - b_f1

        return {
            "before": before_metrics,
            "after": after_metrics,
            "f1_deltas": f1_deltas,
        }

    def compute_coverage(
        self,
        predictions: list[tuple[float, float]],
        ground_truth: list[tuple[float, float]],
        total_duration: float = None,
    ) -> dict[str, float]:
        """
        Analyze what % of the GT highlights are covered by predictions,
        and what % of predictions fall outside GT.

        Args:
            predictions: List of predicted segments.
            ground_truth: List of GT segments.
            total_duration: Total video duration (optional, for context if needed).

        Returns:
            Dict containing coverage percentages.
        """

        def merge_intervals(intervals):
            if not intervals:
                return []
            intervals = sorted(intervals, key=lambda x: x[0])
            merged = [list(intervals[0])]
            for current in intervals[1:]:
                prev = merged[-1]
                if current[0] <= prev[1]:
                    prev[1] = max(prev[1], current[1])
                else:
                    merged.append(list(current))
            return merged

        def get_duration(intervals):
            return sum(end - start for start, end in intervals)

        def get_intersection_duration(int1, int2):
            i, j = 0, 0
            intersection = 0.0
            while i < len(int1) and j < len(int2):
                start = max(int1[i][0], int2[j][0])
                end = min(int1[i][1], int2[j][1])

                if start < end:
                    intersection += end - start

                if int1[i][1] < int2[j][1]:
                    i += 1
                else:
                    j += 1
            return intersection

        merged_preds = merge_intervals(predictions)
        merged_gts = merge_intervals(ground_truth)

        gt_dur = get_duration(merged_gts)
        pred_dur = get_duration(merged_preds)
        overlap = get_intersection_duration(merged_preds, merged_gts)

        gt_coverage = (overlap / gt_dur) if gt_dur > 0 else 0.0
        pred_outside = ((pred_dur - overlap) / pred_dur) if pred_dur > 0 else 0.0

        return {
            "gt_coverage_percent": gt_coverage * 100.0,
            "pred_outside_percent": pred_outside * 100.0,
        }
