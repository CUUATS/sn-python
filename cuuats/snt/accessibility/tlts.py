import pandas as pd
import pandana as pdna
import os
from datetime import timedelta


class Tlts(object):
    def __init__(self, gtfs_path, pandana_network):
        os.chdir(gtfs_path)
        self._set_network(pandana_network)
        self.stop_times = self._set_stop_times()
        self.stops = self._set_stops()
        self.trips = self._set_trips()
        self.routes = self._set_routes()
        self.calendar_dates = self._set_calendar_dates()

    def _set_stop_times(self):
        stop_times_col = ['trip_id', 'arrival_time', 'stop_id',
                          'stop_sequence']
        stop_times = pd.read_csv('stop_times.txt')
        stop_times = stop_times[stop_times_col]
        stop_times.arrival_time = stop_times.arrival_time.apply(
            lambda x: timedelta(hours=int(x[0:2]),
                                minutes=int(x[3:5])))
        return stop_times

    def _set_network(self, pandana_network):
        if isinstance(pandana_network, pdna.Network):
            self.network = pandana_network
        else:
            raise TypeError('pandana_network must be a pandana object')

    def _set_stops(self):
        stops = pd.read_csv('stops.txt')
        x, y = stops.stop_lon, stops.stop_lat
        stops['node_id'] = self.network.get_node_ids(x, y)
        stops_col = ['stop_id', 'node_id', 'stop_lon', 'stop_lat']
        return stops[stops_col]

    def _set_trips(self):
        trips_col = ['route_id', 'service_id', 'trip_id']
        trips = pd.read_csv('trips.txt')
        return trips[trips_col]

    def _set_calendar_dates(self):
        return pd.read_csv('calendar_dates.txt')

    def _set_routes(self):
        return pd.read_csv('routes.txt')

    def filter_trips(self,
                     date,
                     time_range=['07:00:00', '09:00:00']):
        start_time = timedelta(hours=int(time_range[0][0:2]),
                               minutes=int(time_range[0][3:5]))
        end_time = timedelta(hours=int(time_range[1][0:2]),
                             minutes=int(time_range[1][3:5]))
        stop_times = self.stop_times
        calendar_dates = self.calendar_dates
        trips = self.trips
        cond1 = stop_times['arrival_time'] > start_time
        cond2 = stop_times['arrival_time'] < end_time

        peak_stop_times = stop_times[cond1 & cond2]
        peak_trips = pd.merge(peak_stop_times, trips,
                              on='trip_id', how='inner')
        unique_date = calendar_dates.loc[calendar_dates['date'] == date]
        date_peak_trips = pd.merge(peak_trips, unique_date,
                                   on='service_id', how='inner')
        self.date_peak_trips = date_peak_trips
        first_stop = date_peak_trips.loc[date_peak_trips['stop_sequence'] == 1]
        groupby_service = first_stop.groupby(first_stop['service_id'])

        max_arrival = groupby_service.max().arrival_time
        min_arrival = groupby_service.min().arrival_time
        service_count = groupby_service.count().arrival_time
        time_diff = (max_arrival - min_arrival)

        headway = {}
        for item in zip(time_diff.iteritems(), service_count):

            service = item[0][0]
            time = item[0][1]
            count = item[1]
            if time == timedelta():
                headway[service] = timedelta(seconds=3600).seconds
            else:
                headway[service] = (time / (count - 1)).seconds

        self.headway = headway
        return self.date_peak_trips

    def _calculate_headway(self):
        # TODO: calculate the headway
        pass

    def create_transit_network(self):
        stop_nodes_peak = pd.merge(self.date_peak_trips, self.stops,
                                   on='stop_id', how='inner')
        stop_nodes_peak = stop_nodes_peak.sort_values(
                                    ['trip_id', 'stop_sequence'])
        edges = self.network.edges_df
        stop = self.network.nodes_df.index.max() + 1
        nodes = self.network.nodes_df

        headway = self.headway
        prev_trip = None
        # prev_intersection = None
        prev_stop = None
        prev_time = None
        for row in stop_nodes_peak.iterrows():
            intersection = row[1].node_id
            arrival_time = row[1].arrival_time
            trip = row[1].trip_id
            service_id = row[1].service_id
            same_trip = prev_trip == trip

            # TODO: Prevent getting on bus at last stop
            # getting on the bus
            on_bus = pd.DataFrame({'from': [intersection],
                                   'to': [stop],
                                   'weight': [headway.get(service_id, 3600)]},
                                  index=[edges.index.max() + 1])
            edges = edges.append(on_bus)

            # TODO: Prevent getting off bus at first stop
            # getting off the bus
            edges = edges.append(pd.DataFrame({'from': [stop],
                                               'to': [intersection],
                                               'weight': [0]},
                                              index=[edges.index.max() + 1]))

            # transit time between stop
            if prev_stop and same_trip:
                time_diff = (arrival_time - prev_time).seconds
                edges = edges.append(
                    pd.DataFrame({'from': [prev_stop],
                                  'to': [stop],
                                  'weight': [time_diff]},
                                 index=[edges.index.max() + 1]))

            # adding stop to transit nodes
            nodes = nodes.append(
                pd.DataFrame({'x': [row[1].stop_lon],
                              'y': [row[1].stop_lat]},
                             index=[stop])
            )

            prev_trip = trip
            # prev_intersection = intersection
            prev_stop = stop
            prev_time = arrival_time
            stop = stop + 1

        edges['weight'] = edges['weight'].replace(0, 0.01)

        transit_network = pdna.Network(
            node_x=nodes.x,
            node_y=nodes.y,
            edge_from=edges["from"],
            edge_to=edges["to"],
            edge_weights=edges[["weight"]],
            twoway=False
        )
        self.transit_network = transit_network


    def set_poi(self, poi):
        transit_network = self.transit_network
        # set point of interest to find out the weight to nearest poi
        transit_network.set_pois(category="poi",
                                 maxdist=3600,
                                 maxitems=10,
                                 x_col=poi['x'],
                                 y_col=poi['y'])
        nearest_poi = transit_network.nearest_pois(distance=3600,
                                                   category="poi",
                                                   num_pois=2)
        import pdb; pdb.set_trace()