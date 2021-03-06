import os

from pyspark.sql import Row
import luigi
from luigi.contrib.spark import PySparkTask
from pyspark.sql import SparkSession

from bicis.etl.unify_raw_data import UnifyRawData
from bicis.lib.data_paths import data_dir


def _translate_doc(doc):
    res = doc.asDict()
    for date_field in 'rent_date return_date'.split():
        res[date_field + '_day'] = doc[date_field].date()
        res[date_field + '_hour'] = doc[date_field].hour
        res[date_field + '_weekday'] = doc[date_field].isoweekday()
        res[date_field + '_month'] = doc[date_field].replace(day=1).date()
    return Row(**res)

class BuildAllSeries(luigi.WrapperTask):
    def requires(self):
        res = []
        for key in SeriesBuilder.key._choices:
            res.append(SeriesBuilder(key=key))
        return res

class SeriesBuilder(PySparkTask):
    key = luigi.ChoiceParameter(choices=['weekday', 'hour', 'day', 'month'])

    def main(self, sc, *args):
        spark_sql = SparkSession.builder.getOrCreate()

        general_df = (
            spark_sql
                .read
                .load(
                    self.input().path,  # .replace('.csv', '_sample.csv'),
                    format="csv",
                    sep=",",
                    inferSchema="true",
                    header="true")
                .rdd
                .map(_translate_doc)
                .toDF()
        )


        n_rents = (
            general_df
            .groupBy('src_station', 'rent_date_' + self.key)
            .count()
            .withColumnRenamed('count', 'n_rents')
            .withColumnRenamed('src_station', 'station')
            .withColumnRenamed('rent_date_' + self.key, self.key)
        )

        n_returns = (
            general_df
            .groupBy('dst_station', 'return_date_' + self.key)
            .count()
            .withColumnRenamed('count', 'n_returns')
            .withColumnRenamed('dst_station', 'station')
            .withColumnRenamed('return_date_' + self.key, self.key)
        )

        (
            n_rents
            .join(n_returns, ['station', self.key])
            .write
            .csv(self.output().path, header='true')
        )

    def output(self):
        return luigi.LocalTarget(os.path.join(data_dir, 'rents_by_{}.csv'.format(self.key)))

    def requires(self):
        return UnifyRawData()

if __name__ == '__main__':
    luigi.run(main_task_cls=SeriesBuilder)
