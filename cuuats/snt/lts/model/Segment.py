# Segment Class for LTS Assessment
from cuuats.snt.lts import config as c
import pandas as pd
from cuuats.snt.lts.lts_postgis import Lts
from cuuats.snt.lts.model.Approach import Approach
from cuuats.snt.lts.model.BikePath import BikePath


class Segment(object):
    def __init__(self, **kwargs):
        self.bicycle_facility_type = kwargs.get('bicycle_facility_type')
        self.bicycle_facility_width = kwargs.get('bicycle_facility_width')
        self.lanes_per_direction = kwargs.get('lanes_per_direction')
        self.parking_lane_width = kwargs.get('parking_lane_width')
        self.aadt = int(self._remove_none(kwargs.get('aadt')))
        self.functional_class = kwargs.get('functional_class')
        self.posted_speed = kwargs.get('posted_speed')
        self.total_lanes = kwargs.get('total_lanes')
        self.marked_center_lane = kwargs.get('marked_center_lane')

    def _remove_none(self, value):
        if value is None:
            value = 0
        return value

    def _categorize_functional_class(self):
        if self.functional_class is None:
            return "C"
        if self.functional_class >= 4:
            return "C"
        else:
            return "A"

    def _calculate_mix_traffic(self):
        """
        this function calculate the mix traffic scores based on the specify
        criterias
        :param self: self
        :return: np.int64 score
        """
        aadt = self.aadt
        lpd = self.lanes_per_direction
        mix_traffic_score = c.MIXED_TRAF_TABLE
        aadt_scale = c.URBAN_FIX_TRAFFIC_AADT_SCALE
        lane_scale = c.URBAN_FIX_TRAFFIC_LANE_SCALE

        table = pd.DataFrame(mix_traffic_score)
        crits = ([aadt, aadt_scale],
                 [lpd, lane_scale])
        return Lts.calculate_score(table, crits)

    def _calculate_bikelane_with_adj_parking(self, bike_paths):
        parking_lane_width = self.parking_lane_width
        lpd = self.lanes_per_direction
        aadt = self.aadt
        bl_adj_pk_score_one_lane = c.BL_ADJ_PK_TABLE_ONE_LANE
        bl_adj_pk_score_two_lanes = c.BL_ADJ_PK_TABLE_TWO_LANES
        aadt_scale = c.BL_ADJ_PK_AADT_SCALE
        width_scale = c.BL_ADJ_PK_WIDTH_SCALE
        width_scale_two_lanes = c.BL_ADJ_PK_TWO_WIDTH_SCALE

        if parking_lane_width is None:
            return 99

        for bike_path in bike_paths:
            width = bike_path.width
            if width is None:
                return 0

            # No marked lanes or 1 lpd
            if lpd is None or lpd == 1:
                table = pd.DataFrame(bl_adj_pk_score_one_lane)
                crits = ([aadt, aadt_scale],
                         [width, width_scale])
                return (Lts.calculate_score(table, crits))
            # 2 lpd or greater
            else:
                table = pd.DataFrame(bl_adj_pk_score_two_lanes)
                crits = ([aadt, aadt_scale],
                         [width, width_scale_two_lanes])
                return (Lts.calculate_score(table, crits))

    def _calculate_bikelane_without_adj_parking(self, bike_paths):
        parking_lane_width = self.parking_lane_width
        lpd = self.lanes_per_direction
        aadt = self.aadt
        bl_wo_adj_pk_score_one_lane = c.BL_NO_ADJ_PK_TABLE_ONE_LANE
        bl_wo_adj_pk_score_two_lanes = c.BL_NO_ADJ_PK_TABLE_TWO_LANES
        aadt_scale = c.BL_NO_ADJ_PK_AADT_SCALE
        width_scale_one_lane = c.BL_NO_ADJ_PK_WIDTH_SCALE
        width_scale_two_lane = c.BL_NO_ADJ_PK_TWO_WIDTH_SCALE

        if parking_lane_width is None:
            for bike_path in bike_paths:
                width = bike_path.width
                if width is None:
                    return 0
                # no marked lane or 1 lpd
                if lpd is None or lpd == 1:
                    table = pd.DataFrame(bl_wo_adj_pk_score_one_lane)
                    crits = ([aadt, aadt_scale],
                             [width, width_scale_one_lane])
                    return (Lts.calculate_score(table, crits))
                # 2 lps or greater
                else:
                    table = pd.DataFrame(bl_wo_adj_pk_score_two_lanes)
                    crits = ([aadt, aadt_scale],
                             [width, width_scale_two_lane])
                    return (Lts.calculate_score(table, crits))

    def _calculate_right_turn_lane(self, approach):
        lane_config = approach.lane_configuration
        rtl_length = approach.right_turn_lane_length
        bike_lane_approach = approach.bike_lane_approach
        rtl_score = c.RTL_CRIT_TABLE
        straight = "Straight"

        if lane_config is None or \
           self.functional_class is None:
            return 0

        if "R" in lane_config:
            if rtl_length <= 150 and bike_lane_approach is straight:
                return rtl_score[0]
            elif rtl_length > 150 and bike_lane_approach is straight:
                return rtl_score[1]
            else:
                return rtl_score[2]
        elif "Q" in lane_config:
            return rtl_score[3]

        return 0

    def _calculate_left_turn_lane(self, approach):
        lane_config = approach.lane_configuration
        speed = self.posted_speed
        functional_class = self.functional_class
        K = "K"  # dual shared
        L = "L"  # exclusive left turn lane
        dual_shared_score = c.LTL_DUAL_SHARED_TABLE
        ltl_score = c.LTL_CRIT_TABLE
        speed_scale = c.LTL_DUAL_SHARED_SPEED_SCALE
        lane_crossed_scale = c.LTL_CRIT_LANE_CROSSED_SCALE

        if lane_config is None or functional_class is None:
            return 0

        if L in lane_config or K in lane_config:
            table = pd.Series(dual_shared_score)
            crit = [(speed, speed_scale)]
            return Lts.calculate_score(table, crit)
        else:
            table = pd.DataFrame(ltl_score)
            crit = [(speed, speed_scale),
                    (speed, lane_crossed_scale)]
            return Lts.calculate_score(table, crit)

    def blts_score(self, approaches, bike_paths=None, turn_threshold=0):
        rtl_score = 0
        ltl_score = 0

        if bike_paths is None:
            segment_score = self._calculate_mix_traffic()
        else:
            segment_score = Lts._aggregate_score(
                self._calculate_mix_traffic(),
                self._calculate_bikelane_with_adj_parking(bike_paths),
                self._calculate_bikelane_without_adj_parking(bike_paths),
                method='MIN'
            )

        if self.aadt >= turn_threshold:
            for approach in approaches:
                rtl_score = max(rtl_score,
                                self._calculate_right_turn_lane(approach))
                ltl_score = max(ltl_score,
                                self._calculate_left_turn_lane(approach))

        return Lts._aggregate_score(
            segment_score,
            rtl_score,
            ltl_score,
            method='MAX'
        )


if __name__ == '__main__':
    segment = Segment(bicycle_facility_width=6,
                      lanes_per_direction=2,
                      parking_lane_width=None,
                      aadt=3001,
                      functional_class='Major',
                      posted_speed=35)
    approaches = [Approach(lane_configuration="XXTR",
                             right_turn_lane_length=160,
                             right_turn_lane_config="Single",
                             bike_lane_approach="Straight"),
                    Approach(lane_configuration="XXLT",
                             right_turn_lane_length=151,
                             right_turn_lane_config="Dual",
                             bike_lane_approach="Left")]
    bike_paths = [BikePath(width=8)]
    print(segment.blts_score(approaches, bike_paths))
