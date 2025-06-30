import logging
import os
import shutil

import jsonlines
from pyserini.index.__main__ import JIndexCollection
from pyserini.search import SimpleSearcher

logging.basicConfig(level=logging.INFO)

CHUNKSIZE = 100000000


class Ranker(object):

    def index(self):
        pass

    def rank_publications(self, query, page, rpp):
        itemlist = []

        return {
            "page": page,
            "rpp": rpp,
            "query": query,
            "itemlist": itemlist,
            "num_found": len(itemlist),
        }


class Recommender(object):

    def __init__(self):
        self.searcher_publication = None
        self.title_lookup = {}

    def _mkdir(self, dir):
        """Try to create a directory, return the error if not possible.

        Args:
            dir: Directory path to create
        """
        try:
            os.mkdir(dir)
        except OSError as error:
            logging.error(error)

    def _make_chuncks(self, dir):
        """Split all jsonl files from a directory to digestable chunks and save them as jsonl files.

        Args:
            dir: Directory of input files
        """
        for file in os.listdir(dir):
            if file.endswith(".jsonl"):
                with open(os.path.join(dir, file), "r") as f:
                    cnt = 0
                    while True:
                        lines = f.readlines(CHUNKSIZE)
                        if not lines:
                            break
                        with open(
                            "".join(
                                ["/index/chunks/", file[:-6], "_", str(cnt), ".jsonl"]
                            ),
                            "w",
                        ) as _chunk_out:
                            for line in lines:
                                _chunk_out.write(line)
                        cnt += 1

    def _convert_chunks(self, file):
        """Convert jsonl chunk files to a format pyserini can index.
        Args:
            file: Input chunk to process.
        """
        with jsonlines.open(os.path.join("/index/convert/", file), mode="w") as writer:
            with jsonlines.open(os.path.join("/index/chunks/", file)) as reader:
                for obj in reader:
                    title = obj.get("title") or ""
                    title = title[0] if type(title) is list else title

                    abstract = obj.get("abstract") or ""
                    abstract = abstract[0] if type(abstract) is list else abstract

                    try:
                        doc = {
                            "id": obj.get("id"),
                            "contents": " ".join([title, abstract]),
                        }
                        writer.write(doc)
                    except Exception as e:
                        print(e)

    def _create_index(self, index):
        """Create an index and pyserini searcher object for that index.

        Args:
            index: directory name of files to index

        Returns:
            pyserini searcher: searcher for the created index
        """
        logging.info("Creating index for " + index)
        self._mkdir("/index/")
        self._mkdir(os.path.join("/index/", index))
        self._mkdir("/index/convert/")
        self._mkdir("/index/chunks/")
        logging.info("created directories")
        logging.info(os.listdir("/index/"))
        self._make_chuncks(os.path.join("/data/gesis-search/", index))

        for i in os.listdir("/index/chunks/"):
            self._convert_chunks(i)
        shutil.rmtree("/index/chunks")

        args = [
            "-collection",
            "JsonCollection",
            "-generator",
            "DefaultLuceneDocumentGenerator",
            "-threads",
            "1",
            "-input",
            "/index/convert",
            "-index",
            "/index/" + index,
            "-storePositions",
            "-storeDocvectors",
            "-storeRaw",
        ]

        JIndexCollection.main(args)
        shutil.rmtree("/index/convert/")

        return SimpleSearcher("/index/" + index)

    def index(self):
        """Create all indexes for all searcher"""
        self.searcher_publication = self._create_index("documents")

        with jsonlines.open("/data/gesis-search/documents/publication.jsonl") as reader:
            for obj in reader:
                self.title_lookup[obj.get("id")] = obj.get("title")

    def recommend(self, item_id, page, rpp):
        """Create publication recommendations for a given ID.

        Args:
            item_id: Id to create recommendations for
            page: Page number recommendations should be returned for
            rpp: Number recommendations for this page

        Returns:
            dict: Result dictionary of recommended datasets
        """
        itemlist = []

        doc_title = self.title_lookup.get(item_id)
        if doc_title is not None:
            hits = self.searcher_publication.search(doc_title)

            itemlist = [hit.docid for hit in hits[page * rpp : (page + 1) * rpp]]

        return {
            "page": page,
            "rpp": rpp,
            "item_id": item_id,
            "itemlist": itemlist,
            "num_found": len(itemlist),
        }
