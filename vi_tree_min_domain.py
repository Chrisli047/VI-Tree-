from function_utils import (check_function, FunctionProfiler, merge_constraints, get_tight_constraints,
                            check_smallest_intervals)
from sqlite_utils import read_from_sqlite, SQLiteReader
from vertex_utils import create_lookup_table, process_new_vertices

init_constraints = []  # Global variable to store initial constraints

class TreeNode:
    def __init__(self, intersection_id, constraints=None, vertices=None):
        self.intersection_id = intersection_id  # ID of the intersection (record_id)
        self.constraints = constraints if constraints is not None else []  # Constraints for this node, defaults to []
        self.vertices = vertices if vertices is not None else []  # Associated vertices, defaults to []
        self.left_children = None  # Left child
        self.right_children = None  # Right child
        self.skip_flag = False  # Flag to indicate if this node should be skipped
        self.not_enough_vertices = False


class VITree:
    def __init__(self):
        self.root = None  # Initialize the tree with no root

    def insert(self, record_id, constraints, vertices=None, m=None, n=None, db_name=None, conn=None, manager=None):
        """
        Insert a node into the VI tree using a non-recursive method.
        Parameters:
            record_id (int): Intersection ID for the node.
            constraints (list): Constraints for the node.
            vertices (list): Vertices for the node, defaults to an empty list if not provided.
            m (int): Number of functions.
            n (int): Dimension of functions.
            db_name (str): Database file name.
            conn: SQLite database connection.
        """
        global init_constraints

        new_node = TreeNode(record_id, None, vertices)

        if self.root is None:
            # Set the root if the tree is empty
            self.root = new_node

            # Update the global variable and node properties
            init_constraints = constraints
            print(f"Initial constraints for record {record_id}: {init_constraints}")

            # Explicitly set root node properties
            self.root.intersection_id = record_id
            self.root.vertices = vertices if vertices is not None else []

            # Initialize left and right children with constraints
            self.root.left_children = TreeNode(-record_id, [-record_id])
            self.root.right_children = TreeNode(record_id, [record_id])

            left_merged_constraints = merge_constraints(self.root.left_children.constraints, init_constraints, m, n, db_name, conn)
            # print(f"Left merged constraints: {left_merged_constraints}")
            right_merged_constraints = merge_constraints(self.root.right_children.constraints, init_constraints, m, n, db_name, conn)
            # print(f"Right merged constraints: {right_merged_constraints}")

            self.root.left_children.vertices = FunctionProfiler.compute_vertices(left_merged_constraints)
            # print(f"Left children vertices: {self.root.left_children.vertices}")
            self.root.right_children.vertices = FunctionProfiler.compute_vertices(right_merged_constraints)
            # print(f"Right children vertices: {self.root.right_children.vertices}")

            return

        # Use a stack to manage nodes for non-recursive traversal
        stack = [self.root]

        # Set to store previously computed vertices
        previously_computed_vertices = set()
        cache = {}

        while stack:
            # print(len(cache))
            current = stack.pop()
            # Get the record from the database
            # insert_record = FunctionProfiler.read_from_sqlite(m=m, n=n, db_name=db_name, record_id=record_id, conn=conn)
            insert_record = SQLiteReader.get_record_by_id(record_id)
            # print(f"Processing record {record_id}: {insert_record}")

            if not FunctionProfiler.check_function(insert_record, current.vertices, cache=cache):
                continue  # Skip to the next iteration if not satisfied

            if current.left_children is None and current.right_children is None:
                left_merged_constraints = merge_constraints(current.constraints + [-record_id], init_constraints, m, n, db_name, conn)
                # print(f"Left merged constraints: {left_merged_constraints}")
                right_merged_constraints = merge_constraints(current.constraints + [record_id], init_constraints, m, n, db_name, conn)
                # print(f"Right merged constraints: {right_merged_constraints}")

                left_children_vertices = FunctionProfiler.compute_vertices(left_merged_constraints)
                # print(f"Left children vertices: {left_children_vertices}")
                right_children_vertices = FunctionProfiler.compute_vertices(right_merged_constraints)
                # print(f"Right children vertices: {right_children_vertices}")

                if len(left_children_vertices) <= 2 or len(right_children_vertices) <= 2:
                    continue

                # print([current.vertices].count(left_children_vertices),[current.vertices].count(right_children_vertices))
                if [current.vertices].count(left_children_vertices) > 0 or [current.vertices].count(right_children_vertices) > 0:
                    continue
                # result = manager.process_vertex_set(current.vertices)
                # if result:
                #     # print(f"Skipping record {current.intersection_id}: Marked as skippable.")
                #     continue


                current.left_children = TreeNode(
                    -record_id,
                    constraints=[-record_id] + current.constraints
                )

                current.right_children = TreeNode(
                    record_id,
                    constraints=[record_id] + current.constraints
                )

                current.left_children.vertices = left_children_vertices
                current.right_children.vertices = right_children_vertices

                continue

            stack.append(current.left_children)
            stack.append(current.right_children)


    def print_tree_by_layer(self, m, n, db_name, conn):
        """
        Print the VI Tree layer by layer, showing each node's ID, vertices, and database record.
        Handles negative IDs by converting them to positive when fetching records.
        Parameters:
            m (int): Number of functions.
            n (int): Dimension of functions.
            db_name (str): Database file name.
            conn: SQLite database connection.
        """
        if self.root is None:
            print("The tree is empty.")
            return

        # Use a queue to implement level-order traversal, along with layer tracking
        queue = [(self.root, 0)]  # Each element is a tuple (node, layer)
        current_layer = 0
        layer_output = []

        while queue:
            current, layer = queue.pop(0)  # Dequeue the front node

            # Check if we've moved to a new layer
            if layer > current_layer:
                # Print all nodes in the previous layer
                print(f"Layer {current_layer}:")
                for node_output in layer_output:
                    print(node_output)
                print()  # Blank line between layers
                layer_output = []  # Reset the layer output
                current_layer = layer

            # Fetch record from the database
            record_id = abs(current.intersection_id)  # Use positive ID for fetching
            record = read_from_sqlite(m, n, db_name=db_name, record_id=record_id, conn=conn)

            # Add the current node's details to the layer output
            layer_output.append(
                f"Node ID: {current.intersection_id}, Vertices: {current.vertices}, Record: {record}"
            )

            # Enqueue the left and right children if they exist, with incremented layer
            if current.left_children:
                queue.append((current.left_children, layer + 1))
            if current.right_children:
                queue.append((current.right_children, layer + 1))

        # Print the last layer
        print(f"Layer {current_layer}:")
        for node_output in layer_output:
            print(node_output)

    def get_height(self):
        if self.root is None:
            return 0
        # Iterative approach using a queue (BFS)
        from collections import deque
        queue = deque([(self.root, 1)])
        max_depth = 0
        while queue:
            node, depth = queue.popleft()
            if node is not None:
                max_depth = max(max_depth, depth)
                queue.append((node.left_children, depth + 1))
                queue.append((node.right_children, depth + 1))
        return max_depth

    def get_leaf_count(self):
        if self.root is None:
            return 0
        # Iterative approach using a stack (DFS)
        stack = [self.root]
        leaf_count = 0
        while stack:
            node = stack.pop()
            if node is not None:
                # Check if it is a leaf and not flagged as not_enough_vertices
                if node.left_children is None and node.right_children is None and not node.not_enough_vertices:
                    leaf_count += 1
                else:
                    stack.append(node.left_children)
                    stack.append(node.right_children)
        return leaf_count

