import json
from random import randint
from skills_ml.algorithms.string_cleaners import NLPTransforms
from gensim.models.doc2vec import TaggedDocument
from skills_utils.common import safe_get

class CorpusCreator(object):
    """
        A base class for objects that convert common schema
        job listings into a corpus suitable for use by
        machine learning algorithms or specific tasks.

    Example:
    ```python
    from airflow.hooks import S3Hook
    from skills_ml.job_postings.common_schema import job_postings, job_postings_chain
    from skills_ml.job_postings.corpora.basic import CorpusCreator

    s3_conn = S3Hook().get_conn()
    job_postings_generator = job_postings_chain(s3_conn, ['2011Q2'], 'open-skills-private/test_corpus')

    # Default will include all the cleaned job postings
    corpus = CorpusCreator(job_postings_generator)

    # For getting a the raw job postings without any cleaning
    corpus = CorpusCreator(job_postings_generator, raw=True)

    # For using self-defined filter function, one can pass the function like this
    def filter_by_full_soc(document):
        if document['onet_soc_code]:
            if document['onet_soc_code] in ['11-9051.00', '13-1079.99']:
                return document

    corpus = CorpusCreator(job_postings_generator, filter_func=filter_by_full_soc)
    ```


    Attributes:
        job_posting_generator (generator):  an iterable that generates JSON strings.
                                Each string is expected to represent a job listing
                                conforming to the common schema
                                See sample_job_listing.json for an example of this schema
        document_schema_fields (list): an list of schema fields to be included
        filter_func (function): a self-defined function to filter job postings, which takes a job posting as input
                                and output a job posting. Default is to filter documents by major group.
        raw (bool): a flag whether to return the raw documents or transformed documents
    """
    def __init__(self, job_posting_generator=None, document_schema_fields=['description','experienceRequirements', 'qualifications', 'skills'],
                 filter_func=None, raw=False):
        self.job_posting_generator = job_posting_generator
        self.nlp = NLPTransforms()
        self.filter_func = filter_func
        self.filter = self.filter_func
        self.raw = raw
        self.quarters = job_posting_generator.quarters if not job_posting_generator is None else None
        self.document_schema_fields = document_schema_fields

    def raw_corpora(self, job_posting_generator):
        """Transforms job listings into corpus format

        Args:
            job_posting_generator: an iterable that generates JSON strings.
                Each string is expected to represent a job listing
                conforming to the common schema
                See sample_job_listing.json for an example of this schema

        Yields:
            (string) The next job listing transformed into corpus format
        """
        for line in job_posting_generator:
            document = json.loads(line)
            yield self._transform(document)

    def tokenize_corpora(self, job_posting_generator):
        """Transforms job listings into corpus format for gensim's doc2vec
        Args:
            job_posting_generator: an iterable that generates an array of words(strings).
                Each array is expected to represent a job listing(a doc)
                including fields of interests
        Yields:
            (list) The next job listing transformed into gensim's doc2vec
        """
        for line in job_posting_generator:
            document = json.loads(line)
            yield self._transform(document).split()

    def label_corpora(self, job_posting_generator):
        """Extract job label(category) from job listings and transfrom into corpus format

        Args:
            job_posting_generator: an iterable that generates a list of job label (strings).

        Yields:
            (string) The next job label transform into corpus format
        """
        for line in job_posting_generator:
            document = json.loads(line)
            yield str(randint(0,23))

    def _clean(self, document):
        for f in self.document_schema_fields:
            try:
                cleaned = self.nlp.clean_html(document[f]).replace('\n','')
                cleaned = " ".join(cleaned.split())
                document[f] = cleaned
            except KeyError:
                pass
        return document

    def _transform(self, document):
        if self.raw:
            return document
        else:
            return self._clean(document)

    def _join(self, document):
       return self.join_spaces([
           document.get(field, '') for field in self.document_schema_fields
       ])

    def __iter__(self):
        for line in self.job_posting_generator:
            document = json.loads(line)
            if self.filter:
                document = self.filter(document)
                if document:
                    yield self._transform(document)
            else:
                yield self._transform(document)


class SimpleCorpusCreator(CorpusCreator):
    """
        An object that transforms job listing documents by picking
        important schema fields and returns them as one large lowercased string
    """
    join_spaces = ' '.join

    def _clean(self, document):
        return self.join_spaces([
            self.nlp.lowercase_strip_punc(document.get(field, ''))
            for field in self.document_schema_fields
        ])


class Doc2VecGensimCorpusCreator(CorpusCreator):
    """Corpus for training Gensim Doc2Vec
    An object that transforms job listing documents by picking
    important schema fields and returns them as one large cleaned array of words

    Example:
    ```python

    from airflow.hooks import S3Hook
    from skills_ml.job_postings.common_schema import job_postings, job_postings_chain
    from skills_ml.job_postings.corpora.basic import Doc2VecGensimCorpusCreator

    s3_conn = S3Hook().get_conn()
    job_postings_generator = job_postings_chain(s3_conn, ['2011Q2'], 'open-skills-private/test_corpus')

    # Default will include all the job postings with O*NET SOC code.
    corpus = Doc2VecGensimCorpusCreator(job_postings_generator)

    # For using pre-defined major group filter, one need to specify major groups
    corpus = Doc2VecGensimCorpusCreator(job_postings_generator, major_groups=['11', '13'])

    # For using self-defined filter function, one can pass the function like this
    def filter_by_full_soc(document):
        if document['onet_soc_code]:
            if document['onet_soc_code] in ['11-9051.00', '13-1079.99']:
                return document

    corpus = Doc2VecGensimCorpusCreator(job_postings_generator, filter_func=filter_by_full_soc, key=['onet_soc_code'])
    ```

    Attributes:
        job_posting_generator (generator): a job posting generator
        document_schema_fields (list): an list of schema fields to be included
        filter_func (function): a self-defined function to filter job postings, which takes a job posting as input
                                and output a job posting. Default is to filter documents by major group.
        major_groups (list): a list of O*NET major group classes you want to include in the corpus being created.
        key (string): a key indicates the label which should exist in common schema of job posting.

    """
    join_spaces = ' '.join

    def __init__(self, job_posting_generator, document_schema_fields=['description','experienceRequirements', 'qualifications', 'skills'],
                 filter_func=None, major_groups=None, key=['onet_soc_code']):
        super().__init__(job_posting_generator, document_schema_fields, filter_func)
        self.lookup = {}
        self.k = 0 if not self.lookup else max(self.lookup.keys()) + 1
        self.major_groups = major_groups
        self.key = key
        self.filter = self._major_group_filter if isinstance(major_groups, list) else filter_func

    def _clean(self, document):
        return self.join_spaces([
            self.nlp.clean_str(document[field])
            for field in self.document_schema_fields
        ])

    def _major_group_filter(self, document):
        key=self.key[0]
        if document[key]:
            if document[key][:2] in self.major_groups:
                return document

    def _transform(self, document):
        words = self._clean(document).split()
        tag = [self.k]
        return TaggedDocument(words, tag)

    def __iter__(self):
        for line in self.job_posting_generator:
            document = json.loads(line)
            if self.filter:
                document = self.filter(document)
                if document:
                    self.lookup[self.k] = safe_get(document, *self.key)
                    yield self._transform(document)
                    self.k += 1
            else:
                self.lookup[self.k] = safe_get(document, *self.key)
                yield self._transform(document)
                self.k += 1

class Word2VecGensimCorpusCreator(CorpusCreator):
    """
        An object that transforms job listing documents by picking
        important schema fields and returns them as one large cleaned array of words
    """
    join_spaces = ' '.join

    def __init__(self, job_posting_generator, document_schema_fields=['description','experienceRequirements', 'qualifications', 'skills']):
        super().__init__(job_posting_generator, document_schema_fields)

    def _clean(self, document):
        return self.join_spaces([
            self.nlp.clean_str(document[field])
            for field in self.document_schema_fields
        ]).split()


class JobCategoryCorpusCreator(CorpusCreator):
    """
        An object that extract the label of each job listing document which could be onet soc code or
        occupationalCategory and returns them as a lowercased string
    """
    document_schema_fields = [
        'occupationalCategory']

    join_spaces = ' '.join

    def _transform(self, document):
        return self.join_spaces([
            self.nlp.lowercase_strip_punc(document[field])
            for field in self.document_schema_fields
        ])


class RawCorpusCreator(CorpusCreator):
    """
        An object that pass the raw job posting data
    """
    join_spaces = ' '.join

    def __init__(self, job_posting_generator, document_schema_fields=['description','experienceRequirements', 'qualifications', 'skills']):
        super().__init__(job_posting_generator, document_schema_fields)

    def _transform(self, document):
        return self.join_spaces([document[field] for field in self.document_schema_fields])


class RawSentenceCreator(CorpusCreator):
    join_spaces = ' '.join

    def __init__(self, job_posting_generator, document_schema_fields=['description','experienceRequirements', 'qualifications', 'skills']):
        super().__init__(job_posting_generator, document_schema_fields)

    def _transform(self, document):
        return self.nlp.sentence_tokenize(self.join_spaces([document[field] for field in self.document_schema_fields]))

    def __iter__(self):
        for line in self.job_posting_generator:
            document = json.loads(line)
            if self.filter:
                document = self.filter(document)
                if document:
                    for sentence in self._transform(document):
                        yield sentence
            else:
                for sentence in self._transform(document):
                    yield sentence
