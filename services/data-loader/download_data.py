"""
Download ConceptNet data files
"""
import os
import gzip
import shutil
import requests
from tqdm import tqdm
from config import DATA_SOURCES, RAW_DATA_DIR, CHUNK_SIZE


def download_file(url, destination):
    """
    Download a file with progress bar
    """
    print(f"Downloading {url}...")

    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))

    with open(destination, 'wb') as f, tqdm(
        desc=os.path.basename(destination),
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as progress_bar:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            size = f.write(chunk)
            progress_bar.update(size)

    print(f"Downloaded to {destination}")


def decompress_file(compressed_path, output_path):
    """
    Decompress a gzip file
    """
    print(f"Decompressing {compressed_path}...")

    with gzip.open(compressed_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    print(f"Decompressed to {output_path}")


def download_assertions():
    """
    Download and decompress ConceptNet assertions file
    """
    # Ensure raw data directory exists
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    source = DATA_SOURCES['assertions']
    compressed_path = os.path.join(RAW_DATA_DIR, source['filename'])
    uncompressed_path = os.path.join(RAW_DATA_DIR, source['uncompressed'])

    # Check if already downloaded and decompressed
    if os.path.exists(uncompressed_path):
        print(f"Assertions file already exists at {uncompressed_path}")
        file_size = os.path.getsize(uncompressed_path)
        print(f"File size: {file_size / (1024**3):.2f} GB")
        return uncompressed_path

    # Download if compressed file doesn't exist
    if not os.path.exists(compressed_path):
        download_file(source['url'], compressed_path)
    else:
        print(f"Compressed file already exists at {compressed_path}")

    # Decompress
    if not os.path.exists(uncompressed_path):
        decompress_file(compressed_path, uncompressed_path)

    file_size = os.path.getsize(uncompressed_path)
    print(f"Final file size: {file_size / (1024**3):.2f} GB")

    return uncompressed_path


def download_embeddings():
    """
    Download and decompress Numberbatch embeddings file
    """
    # Ensure raw data directory exists
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    source = DATA_SOURCES['embeddings']
    compressed_path = os.path.join(RAW_DATA_DIR, source['filename'])
    uncompressed_path = os.path.join(RAW_DATA_DIR, source['uncompressed'])

    # Check if already downloaded and decompressed
    if os.path.exists(uncompressed_path):
        print(f"Embeddings file already exists at {uncompressed_path}")
        file_size = os.path.getsize(uncompressed_path)
        print(f"File size: {file_size / (1024**2):.2f} MB")
        return uncompressed_path

    # Download if compressed file doesn't exist
    if not os.path.exists(compressed_path):
        download_file(source['url'], compressed_path)
    else:
        print(f"Compressed file already exists at {compressed_path}")

    # Decompress
    if not os.path.exists(uncompressed_path):
        decompress_file(compressed_path, uncompressed_path)

    file_size = os.path.getsize(uncompressed_path)
    print(f"Final file size: {file_size / (1024**2):.2f} MB")

    return uncompressed_path


if __name__ == '__main__':
    print("Starting ConceptNet data download...")
    assertions_file = download_assertions()
    embeddings_file = download_embeddings()
    print(f"Data download complete.")
    print(f"  Assertions: {assertions_file}")
    print(f"  Embeddings: {embeddings_file}")
