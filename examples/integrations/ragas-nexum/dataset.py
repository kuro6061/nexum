"""
dataset.py - Sample QA evaluation dataset for ragas-nexum demo.

Each entry: {question, answer, contexts}
  - question: what the user asked
  - answer: what the RAG pipeline returned
  - contexts: retrieved passages used to generate the answer

Some answers are faithful, some are not (to make evaluation interesting).
"""

EVAL_DATASET = [
    {
        "sample_id": "q01",
        "question": "What is Rust's ownership model?",
        "answer": "Rust's ownership model ensures memory safety without a garbage collector. Each value has exactly one owner, and when the owner goes out of scope, the value is dropped automatically.",
        "contexts": [
            "Rust uses an ownership system to manage memory. Each value has a single owner variable. When the owner goes out of scope, the value is dropped and memory is freed. This eliminates the need for a garbage collector."
        ],
    },
    {
        "sample_id": "q02",
        "question": "How does Python handle memory management?",
        "answer": "Python uses reference counting combined with a cyclic garbage collector to manage memory. Objects are automatically freed when their reference count drops to zero.",
        "contexts": [
            "CPython uses reference counting as its primary memory management technique. Each object tracks how many references point to it. When the count drops to zero, the object is immediately deallocated. A separate cyclic garbage collector handles reference cycles."
        ],
    },
    {
        "sample_id": "q03",
        "question": "What is the difference between TCP and UDP?",
        "answer": "TCP is connection-oriented and guarantees delivery, while UDP is connectionless and faster but may lose packets. TCP uses handshakes; UDP does not.",
        "contexts": [
            "TCP (Transmission Control Protocol) establishes a connection before sending data and guarantees that packets arrive in order. UDP (User Datagram Protocol) sends packets without establishing a connection, making it faster but unreliable."
        ],
    },
    {
        "sample_id": "q04",
        "question": "What is a binary search tree?",
        "answer": "A binary search tree is a sorted tree structure where each node's left child is smaller and right child is larger. Search, insert, and delete all run in O(n) time on average.",  # intentionally wrong: should be O(log n)
        "contexts": [
            "A binary search tree (BST) is a node-based data structure where each node has at most two children. For each node, all values in the left subtree are smaller and all values in the right subtree are larger. Average-case time complexity for search, insert, and delete is O(log n)."
        ],
    },
    {
        "sample_id": "q05",
        "question": "What is Docker and what problem does it solve?",
        "answer": "Docker is a containerization platform that packages applications with their dependencies. It solves the 'works on my machine' problem by ensuring consistent environments across development and production.",
        "contexts": [
            "Docker uses Linux containers to package software and its dependencies together. A Docker container runs the same way on any system that has Docker installed, solving environment inconsistency problems that arise when moving software between development, testing, and production."
        ],
    },
    {
        "sample_id": "q06",
        "question": "What is gradient descent?",
        "answer": "Gradient descent is an optimization algorithm that minimizes a loss function by iteratively moving parameters in the direction of steepest ascent.",  # intentionally wrong: should be steepest descent
        "contexts": [
            "Gradient descent is an iterative optimization algorithm used to minimize a function. It updates parameters by moving in the direction opposite to the gradient (steepest descent). The learning rate controls the step size of each update."
        ],
    },
    {
        "sample_id": "q07",
        "question": "How does HTTPS encrypt web traffic?",
        "answer": "HTTPS uses TLS to encrypt web traffic. During the handshake, asymmetric cryptography establishes a shared symmetric key, which then encrypts all subsequent communication.",
        "contexts": [
            "HTTPS secures HTTP traffic using TLS (Transport Layer Security). The TLS handshake uses asymmetric encryption (public/private keys) to negotiate a shared session key. All subsequent data is encrypted with this symmetric session key for efficiency."
        ],
    },
    {
        "sample_id": "q08",
        "question": "What is a REST API?",
        "answer": "A REST API is an interface that uses HTTP methods to perform operations on resources. REST APIs are stateless, meaning the server stores session information between requests.",  # intentionally wrong: stateless means server does NOT store session
        "contexts": [
            "REST (Representational State Transfer) is an architectural style for APIs. REST APIs use standard HTTP methods (GET, POST, PUT, DELETE) and are stateless  Eeach request contains all information needed to process it, and the server does not store client session state."
        ],
    },
    {
        "sample_id": "q09",
        "question": "What is the CAP theorem?",
        "answer": "The CAP theorem states that a distributed system can only guarantee two of three properties: Consistency, Availability, and Partition tolerance. No system can be fully consistent, available, and partition-tolerant simultaneously.",
        "contexts": [
            "The CAP theorem (Brewer's theorem) states that a distributed data store can only provide two of three guarantees: Consistency (every read receives the most recent write), Availability (every request receives a response), and Partition tolerance (the system continues operating despite network partitions)."
        ],
    },
    {
        "sample_id": "q10",
        "question": "What is memoization?",
        "answer": "Memoization is an optimization technique that caches the results of function calls. When the same inputs occur again, the cached result is returned instead of recomputing.",
        "contexts": [
            "Memoization is a specific form of caching that stores the results of expensive function calls and returns the cached result when the same inputs occur again. It is commonly used to speed up recursive algorithms like Fibonacci computation."
        ],
    },
    {
        "sample_id": "q11",
        "question": "How does a hash table work?",
        "answer": "A hash table uses a hash function to map keys to array indices. Collisions are handled by chaining (linked lists) or open addressing. Average lookup time is O(1).",
        "contexts": [
            "A hash table stores key-value pairs by applying a hash function to the key to determine an array index. When two keys hash to the same index (collision), common strategies include chaining (each bucket holds a linked list) or open addressing (probing for the next empty slot). Average-case time complexity is O(1) for insertion, lookup, and deletion."
        ],
    },
    {
        "sample_id": "q12",
        "question": "What is overfitting in machine learning?",
        "answer": "Overfitting occurs when a model learns the training data too well, including noise, and performs poorly on unseen data. It can be reduced with regularization, dropout, or more training data.",
        "contexts": [
            "Overfitting happens when a machine learning model becomes too complex and fits the training data too closely, including its noise and outliers. The model performs well on training data but poorly on new, unseen data. Common remedies include regularization (L1/L2), dropout, early stopping, and collecting more training data."
        ],
    },
    {
        "sample_id": "q13",
        "question": "What is the difference between a process and a thread?",
        "answer": "A process is an independent program with its own memory space. Threads share memory within a process and are lighter weight. Context switching between threads is faster than between processes.",
        "contexts": [
            "A process is an independent program instance with its own isolated memory space. Threads are execution units within a process that share the same memory. Creating and switching threads is cheaper than processes, but shared memory requires synchronization to avoid race conditions."
        ],
    },
    {
        "sample_id": "q14",
        "question": "What is SQL injection?",
        "answer": "SQL injection is a security vulnerability where attackers insert malicious SQL code into input fields, allowing them to manipulate or access the database. Prevention includes parameterized queries.",
        "contexts": [
            "SQL injection is an attack where malicious SQL statements are inserted into input fields, which are then executed by the database. Attackers can bypass authentication, read sensitive data, or destroy data. The primary defense is using parameterized queries or prepared statements."
        ],
    },
    {
        "sample_id": "q15",
        "question": "What is eventual consistency?",
        "answer": "Eventual consistency guarantees that, if no new updates are made to a distributed system, all nodes will eventually agree on the same value. It is used in systems that prioritize availability over strict consistency.",
        "contexts": [
            "Eventual consistency is a consistency model used in distributed systems. It guarantees that if no new updates are made to a given data item, eventually all accesses to that item will return the last updated value. Systems like Amazon DynamoDB use eventual consistency to achieve high availability."
        ],
    },
]
